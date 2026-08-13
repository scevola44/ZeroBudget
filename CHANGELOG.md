# Changelog

## [0.6.0-beta.10](https://github.com/scevola44/ZeroBudget/compare/v0.5.1-beta.10...v0.6.0-beta.10) (2026-08-13)


### Features

* add Today button to Budget page month navigator ([#126](https://github.com/scevola44/ZeroBudget/issues/126)) ([a57c3e7](https://github.com/scevola44/ZeroBudget/commit/a57c3e7fb0ec5ca24d62779a12be2dc4cd67d2b9))
* redesign mobile Transactions page with tappable cards and quick add ([#125](https://github.com/scevola44/ZeroBudget/issues/125)) ([c74f257](https://github.com/scevola44/ZeroBudget/commit/c74f257660088f77a16b2f529d1a77cea21ebe59))
* show grouped, color-coded remaining budget in the category picker ([#127](https://github.com/scevola44/ZeroBudget/issues/127)) ([fa0aad6](https://github.com/scevola44/ZeroBudget/commit/fa0aad6a14896d22195c3c1fa1082142f38f875f))


### Bug Fixes

* stop iOS date picker from auto-opening in edit transaction modal ([#123](https://github.com/scevola44/ZeroBudget/issues/123)) ([2305276](https://github.com/scevola44/ZeroBudget/commit/23052760532f6f9a66ff176493b0c341da7cb9c0))

## [0.5.1-beta.10](https://github.com/scevola44/ZeroBudget/compare/v0.5.0-beta.10...v0.5.1-beta.10) (2026-08-13)


### Bug Fixes

* move Ready to Assign when a transfer crosses the on-budget boundary ([#121](https://github.com/scevola44/ZeroBudget/issues/121)) ([c4e1090](https://github.com/scevola44/ZeroBudget/commit/c4e1090d050ff6bc9011a1111c9bcfe1632eeb0b))

## [0.5.0-beta.10](https://github.com/scevola44/ZeroBudget/compare/v0.4.0-beta.10...v0.5.0-beta.10) (2026-08-13)


### Features

* allow deleting transactions from the Transactions page ([#118](https://github.com/scevola44/ZeroBudget/issues/118)) ([ad1cf78](https://github.com/scevola44/ZeroBudget/commit/ad1cf78bacd7eb08db26f69cd172fab3ea2763b1))
* mass-delete transactions with row selection and filtered select-all ([#120](https://github.com/scevola44/ZeroBudget/issues/120)) ([dd85a87](https://github.com/scevola44/ZeroBudget/commit/dd85a87c17a922b749d8327bf0c96e694ed63121))


### Bug Fixes

* reuse existing bank connection/accounts on reconnect, sync month-to-date on first link ([#117](https://github.com/scevola44/ZeroBudget/issues/117)) ([b47d841](https://github.com/scevola44/ZeroBudget/commit/b47d8419bf556dffcc26bb27758e4f37f4cd495b))

## [0.4.0-beta.10](https://github.com/scevola44/ZeroBudget/compare/v0.3.0-beta.10...v0.4.0-beta.10) (2026-08-12)


### Features

* set default category filter to Unassigned in Transactions page ([#114](https://github.com/scevola44/ZeroBudget/issues/114)) ([8189f89](https://github.com/scevola44/ZeroBudget/commit/8189f89c46ae665d992fb3b40d4bf5a06d4accd2))


### Bug Fixes

* never count unassigned outgoing money as an Insights expense ([#116](https://github.com/scevola44/ZeroBudget/issues/116)) ([792f7b1](https://github.com/scevola44/ZeroBudget/commit/792f7b18cfdf1c00654fb2d0ad04c558f9facb91))

## [0.3.0-beta.10](https://github.com/scevola44/ZeroBudget/compare/v0.2.0-beta.10...v0.3.0-beta.10) (2026-08-12)


### Features

* add unassigned-transactions notification island ([#111](https://github.com/scevola44/ZeroBudget/issues/111)) ([ecec92d](https://github.com/scevola44/ZeroBudget/commit/ecec92d759383015b8c8a1114ff54f5430ff4ee9))

## [0.2.0-beta.10](https://github.com/scevola44/ZeroBudget/compare/v0.1.1-beta.10...v0.2.0-beta.10) (2026-08-12)


### Features

* add a manual Ready to Assign flag for transactions ([#101](https://github.com/scevola44/ZeroBudget/issues/101)) ([05dce0f](https://github.com/scevola44/ZeroBudget/commit/05dce0fca8770d7707bf98f55ea49fbd3c41d9fb))
* detect and manually mark transfers to unsynced accounts ([#99](https://github.com/scevola44/ZeroBudget/issues/99)) ([37abb79](https://github.com/scevola44/ZeroBudget/commit/37abb79130efe9719f9c1afe043f985bd3dbc59a))


### Bug Fixes

* exclude linked transfers from the Unassigned category filter ([#100](https://github.com/scevola44/ZeroBudget/issues/100)) ([b217bea](https://github.com/scevola44/ZeroBudget/commit/b217bea8012c39e1cc1e3576e269fa8040eb23ed))
* monthly goal need suggestion ignores in-month spending ([#103](https://github.com/scevola44/ZeroBudget/issues/103)) ([89194a5](https://github.com/scevola44/ZeroBudget/commit/89194a5df7ab0563d06ef712a87632e4b73c1d9f))
* register root package in release-please-config.json ([#107](https://github.com/scevola44/ZeroBudget/issues/107)) ([1004cb4](https://github.com/scevola44/ZeroBudget/commit/1004cb452c79b78849522df5a61b052b352e7b9e))
