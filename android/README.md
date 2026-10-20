# Android 壳（未编译，代码可直接用）

目标：把 `app/` 原样塞进 `assets/`，一个 Activity + `WebViewAssetLoader`，就是一个能装的离线 App。

本机没有 Android SDK，所以这里只给**完整可粘贴的代码**，没有构建产物。

---

## 1. 放内容

```bash
python3 pipeline/pack.py
mkdir -p android/app/src/main/assets/shizi
unzip -o dist/shizi-web.zip -d android/app/src/main/assets/shizi
```

目录应是：

```
android/app/src/main/assets/shizi/index.html
android/app/src/main/assets/shizi/data.js
android/app/src/main/assets/shizi/assets/audio/*.mp3
android/app/src/main/assets/shizi/manifest.json
```

## 2. 依赖

`app/build.gradle`：

```gradle
dependencies {
    implementation "androidx.appcompat:appcompat:1.7.0"
    implementation "androidx.webkit:webkit:1.11.0"
}
```

## 3. Manifest（注意：没有 INTERNET 权限）

```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <!-- 故意不声明 INTERNET：这个 App 从物理上没有联网能力 -->
    <application
        android:allowBackup="false"
        android:hardwareAccelerated="true"
        android:usesCleartextTraffic="false"
        android:label="小书"
        android:theme="@style/Theme.AppCompat.Light.NoActionBar">

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:configChanges="orientation|screenSize|keyboardHidden"
            android:windowSoftInputMode="adjustResize">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

## 4. MainActivity.kt

```kotlin
package com.example.shizi

import android.annotation.SuppressLint
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.WindowManager
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import androidx.appcompat.app.AppCompatActivity
import androidx.webkit.WebViewAssetLoader
import androidx.webkit.WebViewClientCompat

class MainActivity : AppCompatActivity() {

    private lateinit var web: WebView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 发布版关掉调试；调试时可以在 chrome://inspect 里看
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)

        val loader = WebViewAssetLoader.Builder()
            .addPathHandler("/shizi/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()

        web = WebView(this).apply {
            setBackgroundColor(Color.parseColor("#FBF6EC"))
            overScrollMode = View.OVER_SCROLL_NEVER
            isVerticalScrollBarEnabled = false
            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true            // localStorage：学习记录
                mediaPlaybackRequiresUserGesture = false
                allowFileAccess = false             // 只走 assets，不碰文件系统
                allowContentAccess = false
                textZoom = 100                      // 不跟随系统字号，避免排版崩
                cacheMode = android.webkit.WebSettings.LOAD_NO_CACHE
            }
            webViewClient = object : WebViewClientCompat() {
                override fun shouldInterceptRequest(
                    view: WebView,
                    request: WebResourceRequest
                ): WebResourceResponse? = loader.shouldInterceptRequest(request.url)

                // 任何外链都不放行：这是一个离线绘本，不该有"跳出去"的路径
                override fun shouldOverrideUrlLoading(
                    view: WebView,
                    request: WebResourceRequest
                ): Boolean = true
            }
            loadUrl("https://appassets.androidplatform.net/shizi/index.html")
        }

        setContentView(web)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
    }

    /** 返回键先交给页面；页面没处理再退出。 */
    override fun onBackPressed() {
        web.evaluateJavascript("window.shiziBack ? shiziBack() : false") { result ->
            if (result != "true") finish()
        }
    }

    override fun onPause() {
        super.onPause()
        web.onPause()
        web.pauseTimers()
    }

    override fun onResume() {
        super.onResume()
        web.resumeTimers()
        web.onResume()
    }

    override fun onDestroy() {
        web.destroy()
        super.onDestroy()
    }
}
```

## 5. 需要知道的四个坑

1. **音频要用户先摸一下屏幕。** Android WebView 的自动播放限制比浏览器松一点，但仍建议首次进入时由 `pointerdown` 解锁 `AudioContext`（本 Demo 用 `<audio>`，点字即用户手势，没问题）。
2. **不要把 `data.js` 和音频打进 APK 之外的目录。** `WebViewAssetLoader` 只认 `assets/`，`file://` 在 Android 上会被 `allowFileAccess=false` 拦掉。
3. **`INTERNET` 权限删掉之后，任何 CDN 字体/图标都会失败。** 本 Demo 已经全部本地化（系统字体 + 内联 SVG），这就是为什么它敢删。
4. **锁屏/来电会打断音频。** WebView 会自己丢焦点；如果要做"读到一半接着读"，需要在 `onPause` 里记页码（localStorage 已经存了上次课程）。

## 6. 验收清单

- [ ] 飞行模式下能打开、能点读、能翻页
- [ ] 设置里看应用权限：没有"网络"一项
- [ ] 冷启动到第一页 < 1.5s（中端机）
- [ ] 点字到出声 < 100ms（Demo 在桌面 Chromium 上约 12–40ms）
- [ ] 家长面板能导出 JSON，文件能在电脑上被 `pipeline/report.py` 读
- [ ] 按返回键不会在读到一半时直接退出（或明确做成退出，别半死不活）
