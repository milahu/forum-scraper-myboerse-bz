{ pkgs ? import <nixpkgs> {} }:

with pkgs;

mkShell {
  buildInputs = [
    # gnumake # make
    # node-gyp
    # node-gyp-build
    # python3 # for node-gyp
    (python3.withPackages (pp: with pp; [
      requests
      # distutils # for node-gyp
      beautifulsoup4
      # playwright
      nur.repos.milahu.python3.pkgs.patchright
      # playwright
      # rapidfuzz
      guessit
    ]))
  ];

  # fix: Could not start dynamically linked executable: /home/user/.cache/ms-playwright/chromium_headless_shell-1228/chrome-headless-shell-linux64/chrome-headless-shell
  # https://github.com/NixOS/nixpkgs/issues/268004
  # Package Python Playwright with Browser
  PLAYWRIGHT_BROWSERS_PATH = "${pkgs.playwright-driver.passthru.browsers}";
}
