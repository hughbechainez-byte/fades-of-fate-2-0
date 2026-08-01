[app]
title = The Fades of Fate
package.name = thefadesoffate
package.domain = com.hughbechainezbyte.thefadesoffate
source.dir = ..
source.include_exts = py,png,jpg,jpeg,wav,ogg,mp3,json,txt
source.include_patterns = main.py,src/**/*.py,assets/**/*,data/**/*
source.exclude_patterns = .git, .venv, .github, build, dist, logs, tmp, .mypy_cache, tests
version = 0.15.0
requirements = python3,cython==0.29.36,pygame==2.5.2
p4a.branch = master
p4a.commit = 957a3e5f8c270f7aa648ba185e5a68c1077a798d
orientation = landscape
fullscreen = 1
android.permissions = INTERNET, WRITE_EXTERNAL_STORAGE
android.api = 30
android.minapi = 21
android.ndk = 25b
android.accept_sdk_license = True
android.allow_skip_permissions = True
android.arch = arm64-v8a

[buildozer]
log_level = 2
