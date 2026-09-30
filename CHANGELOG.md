# Changelog

## [0.3.0](https://github.com/trois-six/aioteleco/compare/v0.2.0...v0.3.0) (2026-09-30)


### Features

* **cli:** add memory, radio-counter and radio-decode commands ([33f3448](https://github.com/trois-six/aioteleco/commit/33f344883f95c7a49aee4ffab00ac0428b3948e3))
* **hub:** read the box memory and its radio serials and counters ([5b8cd1c](https://github.com/trois-six/aioteleco/commit/5b8cd1c41effe1b63cea52cb568ae6cadf45d781))
* **radio:** decode counter bit 9, extending the rolling code to 1023 ([15df8d6](https://github.com/trois-six/aioteleco/commit/15df8d6c5dd6f01aa8dca2bd006dc6683986e4a3))
* **radio:** decode the rolling code (bytes 0..4 of a frame) ([2b50945](https://github.com/trois-six/aioteleco/commit/2b50945f6d55e6ec7945cb7426cd515677007f57))
* **radio:** model the 868 MHz frames the box sends to the receivers ([38330a9](https://github.com/trois-six/aioteleco/commit/38330a9e51cd8c44836fb336e246bc9217b3391a))


### Bug Fixes

* **radio:** cap the rolling-code counter at 511, the bits the model covers ([f60033b](https://github.com/trois-six/aioteleco/commit/f60033bdcf8684e1f1e161256877dd16f679e68e))


### Documentation

* **hub:** TEST_SCAN is a Wi-Fi scan, not a radio scan ([e93dd49](https://github.com/trois-six/aioteleco/commit/e93dd49498c5c1a4bccbb12af1795a48b1ba61c7))
* **protocol:** document the radio link, the box memory map and firmware updates ([34b43b3](https://github.com/trois-six/aioteleco/commit/34b43b39abd32db959e88ad37dbb77c7e4f62e8d))
* **radio:** document the rolling-code algorithm ([799e737](https://github.com/trois-six/aioteleco/commit/799e73769be838f20a9a3c5ad19e2d4d96b5d81d))
* **radio:** mark counter bit 9 and the seed permutation as unverified ([5743423](https://github.com/trois-six/aioteleco/commit/5743423326d82c8d59956592a826fb11325f8e86))
* **radio:** record counter bit 9 as solved (counters 0..1023) ([e819ee9](https://github.com/trois-six/aioteleco/commit/e819ee997d5ab9529b025e8085b91c82e4c8d0ca))
* **radio:** record the batch dedup, transmitter offset and MEMORY scope ([2e82b1b](https://github.com/trois-six/aioteleco/commit/2e82b1bfc5b72ec3085ed2355ff2186b293679f6))
* **radio:** record the full session findings ([af05ade](https://github.com/trois-six/aioteleco/commit/af05adec2769a37337db55f1b3ed176cfe44c1e7))
* **readme:** refresh the PyPI badge ([7daff73](https://github.com/trois-six/aioteleco/commit/7daff7368f64fee2fab3eefb6eca9daf8e340f9e))

## [0.2.0](https://github.com/trois-six/aioteleco/compare/v0.1.0...v0.2.0) (2026-09-24)


### Features

* **cover:** expose the move direction and restore a saved position ([d63cba8](https://github.com/trois-six/aioteleco/commit/d63cba8bc93dad408b7394337b2eba6796fb1583))


### Bug Fixes

* **cli:** save the calibrated travel times to the config file ([f3dc914](https://github.com/trois-six/aioteleco/commit/f3dc91497d1aa2d5737e28186d45419401a5eff1))

## 0.1.0 (2026-09-24)


### Features

* aioteleco, async SDK and CLI for Teleco Automation boxes ([abbe753](https://github.com/trois-six/aioteleco/commit/abbe7536ab03ec48be08ad11e042d66c799b6b48))
* **cli:** add 'teleco light level' for the free dimmer level ([3f8b266](https://github.com/trois-six/aioteleco/commit/3f8b266fa482b2f21562a978e802e753acd49841))
* **cover:** reach any position by timing a move then sending STOP ([f82d27c](https://github.com/trois-six/aioteleco/commit/f82d27c951f032a74fd93602b3c285ffb08ed36f))
* implement every box command and flow of the app ([54cd9af](https://github.com/trois-six/aioteleco/commit/54cd9afb4f64837ef825a70b713cab6442d0a6b8))
* **scripts:** add a read-only probe of a real account ([727783a](https://github.com/trois-six/aioteleco/commit/727783ae48c4eca45fb70a50a7620a705a90f9e9))
* **timers:** delete a device timer the way the app does ([c265810](https://github.com/trois-six/aioteleco/commit/c265810e85f37bb6fc00357dcf5a29f06dc03125))


### Bug Fixes

* **devices:** map dimmer levels to steps and derive cover positions like the app ([4d53de7](https://github.com/trois-six/aioteleco/commit/4d53de7f3854857c57fc9399adb630c0845c2989))
* **hub:** identify the timer save_timer creates by its new id ([9435e96](https://github.com/trois-six/aioteleco/commit/9435e96b34a99f57ed9a32f60bcab5dff4bd8edf))


### Documentation

* add an API documentation site with mkdocs-material and mkdocstrings ([beb1aea](https://github.com/trois-six/aioteleco/commit/beb1aeacddcc409d518c6a544302dfaf0d9787f7))
* add security policy, contributing guide and GitHub templates ([d317f98](https://github.com/trois-six/aioteleco/commit/d317f9868cec22399afd24669209bd70455132eb))
* **protocol:** document box scenarios, board sync, remotes and timer deletion ([efb9589](https://github.com/trois-six/aioteleco/commit/efb9589f63ffc913e22de63fb817df009c0e2bcd))
* **protocol:** make the protocol notes an OKF v0.2 bundle ([9b598d5](https://github.com/trois-six/aioteleco/commit/9b598d547271db6f2f8f8747074a50902058ae32))
* **readme:** link the documentation site ([380020a](https://github.com/trois-six/aioteleco/commit/380020a8b2d268d27581f1c64fd81cb904aa9a96))
* **readme:** present aioteleco for every Teleco brand app ([8c3235e](https://github.com/trois-six/aioteleco/commit/8c3235ea09c6f792b86f282db3c98c49642aedbf))
