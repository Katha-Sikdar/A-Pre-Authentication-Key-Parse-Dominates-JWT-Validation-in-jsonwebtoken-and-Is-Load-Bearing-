# VM B: the x86_64 cloud VM used for the JSS revision runs (2026-09-30)

`machine.txt` is `lscpu`, `/etc/os-release`, `uname -a`, `nproc` and `free -g`
captured on the VM that produced every `2026-09-30*` run in `data/runs/`.
It is a different instance, with a different CPU model and clock, from the
x86_64 VM of 2026-09-24 ("VM A": Intel Xeon @ 2.80GHz, see the
`host.cpu_model` field of `2026-09-24T17-10-07Z-openssl-c-probe/run_metadata.json`).
VM A was a per-session cloud VM and was no longer available, so the revision
runs could not be repeated on it; absolute values from the two VMs are not
comparable.
