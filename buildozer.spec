[app]
title = MAZE GAME
# The package id is PERMANENT once the app is on Google Play: change it to your own (reverse domain)
# before publishing. For test APKs it does not matter.
package.name = mazegame
package.domain = org.mazegame
version = 0.1.0

source.dir = .
source.include_exts = py,png,jpg,json,ttf,wav,ogg,atlas
source.exclude_dirs = tests, docs, backend, tools, .github, .git, bin, .buildozer, .pytest_cache, __pycache__, platforms
source.exclude_patterns = *.example, requirements*.txt, pytest.ini, README.md, .env*, *.sql

# certifi: Android's Python has no CA store, needed for HTTPS to Supabase
requirements = python3,kivy==2.3.0,certifi

icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/presplash.png
orientation = portrait
fullscreen = 0

# Network access is required for accounts, cloud save and the daily challenge
android.permissions = INTERNET
android.api = 34
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a
android.accept_sdk_license = True
android.release_artifact = aab

[buildozer]
log_level = 2
warn_on_root = 1
