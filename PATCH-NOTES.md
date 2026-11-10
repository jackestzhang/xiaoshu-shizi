# RPG v1.0 · 方案 A 修复补丁

基线：`v0.9.2-reader` / `54b21ea`（对应 GitHub main `29b96c5` 的文件树）
分支：`rpg`

## 决策

采用方案 A：保留底图人物，对话框角使用 96×96 圆形头像。

- p1 仍用 `L03_p1_bg.webp`，dialog 模式把 reader 的三段式 rig 贴回去，遮住补洞并保留呼吸/锄地/沉腰/直腰。
- p2–p7 使用原画（人物已在底图），不再叠加 `_torso` 探头像。
- 新增 `app/assets/actors/L03_farmer_avatar.webp`（192×192，CSS 显示 96×96 圆形）。
- `.story.is-dialog` 强制单列满宽，修掉 1280 桌面右侧约 600px 空白。

## 应用

```bash
git checkout rpg
git apply --binary rpg-planA.patch
make build     # 重新生成 app/data.js 与对话音频
make check
make demo      # dist/shizi-demo.html
```

补丁未包含 `app/assets/audio/*.mp3`：它们是 `pipeline/build.py` 按台词内容哈希生成的，
`make build` 会补齐。若离线环境需要，使用同目录下的音频包。
