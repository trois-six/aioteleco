# aioteleco

Unofficial async Python SDK and command-line tool (`teleco`) for **Teleco Automation**
boxes: the home-automation box behind the *Daisy Teleco* app and the apps Teleco builds
for other brands. It drives pergolas (slats, retractable roofs), awnings, screens,
shutters, lights (on/off, dimmers, RGB, tunable white), heaters and more.

It talks to the Teleco cloud like the official apps do and, when the box is reachable on
your network, sends commands **directly to the box over the LAN**.

!!! warning
    This project is not affiliated with, nor endorsed by, Teleco Automation or any of the
    brands listed below. It is based on the analysis of the Android app for
    interoperability. Brand names are trademarks of their respective owners. The devices
    it drives are motorised: test with the equipment in sight.

## Supported apps

Every brand app that uses a cloud account talks to the same Teleco cloud and the same
box, so an account created in any of them works with aioteleco: Daisy Teleco, Biossun,
Brustor, Durmi, Gibus, Hardtop, Kettal, Pratic and Wise.

The "direct" apps that work without a cloud account are not covered.

## Highlights

* **Cloud and LAN.** Commands go to the box over the LAN when its address is known and
  fall back to the cloud; state is read from the cloud.
* **No hard-coded command ids.** Every device receives its own list of commands from the
  cloud; the SDK picks the right one the way the app does.
* **Typed devices.** Covers, slats, lights, dimmers, RGB and tunable white lights,
  heaters, fans, audio, each with its own methods.
* **Box management.** Scenarios, timers, remotes, box queries and diagnostics.
* **Anonymised diagnostics.** `teleco diagnose` dumps an account without personal data,
  ready to attach to a bug report.

## Where to go next

* [Getting started](getting-started.md): install, command line, first script.
* [API reference](reference/index.md): every public class and helper.
* [Protocol notes](protocol/index.md): how the app talks to the cloud and to the box.
