# Intermediate versions: bounded offline audit

Already-extracted installer resources were inspected statically. No Story application, installer, recovered frontend code, network request, production configuration or paid provider was used.

## Verified findings

- Embedded `frontend/assets/index-C39RdfcR.js` identifies itself as **1.24.6**. Its import graph and the 1.24.5 baseline each contain **44 modules**.
- The added Chinese UI message families between those graphs are `index.js` (generator startup warnings and same-email/reinstall explanation) and `PlaygroundPage-DdjAl5e7.js` (next-cover reset with retained template/style/ratio/gallery). This establishes an intermediate code baseline; it is not official release-note text.
- No embedded 1.24.6–1.24.9 release-note prose was found. Extracted text contains no literal 1.24.7/1.24.8/1.24.9. Neither inspected native binary contains literal versions 1.24.6–1.24.9.
- `frontend/asset-manifest.json` inventories **1,952 assets**: 1,853 JS, 71 CSS, 14 WebP, 6 JPG, 4 WOFF2, 2 SVG, 1 HTML and 1 PNG. No Markdown/release-history asset is listed.
- Both intermediate/current entry bundles invoke native `check_update` and render returned `notesMd`; announcements use `/v1/announcements?productId=…`. Both native executables contain `/v1/update/check`, `src\updater.rs`, and `UpdateInfo` fields `notesMd`, `forceUpdate`, `publishedAt`. See existing `update-entry.json` and `reused-1245-update-entry.json`.
- After excluding compressed frontend payloads, the native scans each found 113 Chinese string tokens and no meaningful new component/account message. API-route and Rust-source-path sets had no additions/deletions.

## Source hashes

- `baseline1245`: `D:\1Leida-shipinhao\074-copy-rewrite\.desktop-tools\story1245-audit\frontend\assets\index-BL1mWGtO.js` — SHA-256 `6f37593fe69c907193baf63463cd0922d7859f1e41ef3a734a378217da800732`
- `embedded1246`: `D:\1Leida-shipinhao\074-copy-rewrite\.desktop-tools\story1250-audit\frontend\assets\index-C39RdfcR.js` — SHA-256 `f6a28c626e046ba45fb58ad4d1c090a2a61d24c309153b8ecd3b080d2afd31a1`
- `active1250`: `D:\1Leida-shipinhao\074-copy-rewrite\.desktop-tools\story1250-audit\frontend\assets\index-BjfyS2m-.js` — SHA-256 `f284b1102d2d12bfb6802e5b57a55855553247241839188244f0bdeb54a9dc4b`

## Limits

Literal/string absence does not prove that intermediate releases did not exist or that every fix is covered. UI-message and native-string comparisons do not prove complete semantic or runtime parity. No remote release-note body was obtained by this offline audit. Parent documentation/HEAD investigations are separate and not independently verified here.

Full structured evidence and source paths are in `intermediate-offline-audit.json`.
