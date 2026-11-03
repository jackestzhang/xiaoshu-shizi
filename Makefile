.PHONY: build demo check ui pack all clean publish

build:
	python3 pipeline/build.py

check:
	python3 tests/run_checks.py

ui:
	python3 tests/ui_check.py
	python3 tests/layout_check.py
	python3 tests/bundle_check.py
	python3 tests/picto_check.py
	python3 tests/touch_check.py

demo: build
	python3 pipeline/bundle.py

pack: demo
	python3 pipeline/pack.py

# 传到资料库「识字绘本 · 演示」，标题带日期和提交号
publish: demo
	python3 pipeline/publish.py

all: check ui pack

clean:
	rm -rf dist review/*.html app/assets/audio/*.mp3
	find . -name '__pycache__' -type d -exec rm -rf {} +
