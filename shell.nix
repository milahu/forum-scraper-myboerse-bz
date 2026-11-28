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
      rapidfuzz
      guessit
      nur.repos.milahu.python3.pkgs.camoufox
      cryptography
    ]))
  ];

  FIREFOX_ADDON_DARKREADER = nur.repos.milahu.python3.pkgs.camoufox.firefox-addons.darkreader;
}
