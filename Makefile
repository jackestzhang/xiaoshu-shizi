.PHONY: build demo check ui pack all clean

build:
	python3 pipeline/build.py

check:
	python3 tests/run_checks.py

ui:
	python3 tests/ui_check.py
	python3 tests/bundle_check.py
	python3 tests/picto_check.py

demo: build
	python3 pipeline/bundle.py

pack: demo
	python3 pipeline/pack.py

all: check ui pack

clean:
	rm -rf dist review/*.html app/assets/audio/*.mp3
	find . -name '__pycache__' -type d -exec rm -rf {} +
