from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AndroidPackagingTests(unittest.TestCase):
    def test_local_pygame_recipe_links_arm64_simd_sources(self) -> None:
        spec = (ROOT / "android" / "buildozer.spec").read_text(encoding="utf-8")
        recipe = (ROOT / "android" / "recipes" / "pygame" / "__init__.py").read_text(
            encoding="utf-8"
        )
        patch = (
            ROOT
            / "android"
            / "recipes"
            / "pygame"
            / "patches"
            / "include-android-simd-sources.patch"
        ).read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "android-apk-release.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("p4a.local_recipes = ./recipes", spec)
        self.assertIn("include-android-simd-sources.patch", recipe)
        self.assertIn("src_c/simd_blitters_sse2.c", patch)
        self.assertIn("src_c/simd_blitters_avx2.c", patch)
        self.assertIn("android-ndk-r25b/toolchains/llvm", workflow)
        self.assertIn("test -x \"$LLVM_READELF\"", workflow)


if __name__ == "__main__":
    unittest.main()
