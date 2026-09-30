# Support status of Ubuntu 24.04's nodejs package (revision item 5)

Evidence, captured 2026-09-30 from the environment used for the revision:

- `apt_nodejs.txt`: `apt-cache policy/madison/show nodejs` inside
  `psao/distro-node:ubuntu24.04` (ubuntu:24.04 + `apt-get install nodejs`).
  The only published version is `18.19.1+dfsg-6ubuntu5`, in `noble/universe`;
  no newer version in noble-updates or noble-security.
- `ubuntu_release_cycle_excerpt.txt`: sentences mentioning "Universe" on
  https://ubuntu.com/about/release-cycle. Universe is "community and extra
  packages"; security coverage for Universe is provided by Expanded Security
  Maintenance through Ubuntu Pro.

The manuscript states only what these files show.
