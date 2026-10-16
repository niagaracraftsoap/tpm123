# `tpm123`

`tpm123` securely unseals TPM 1.2-sealed secrets at boot and writes them into per-user, tmpfs-based environment files under `/run/<user>/`.

Secrets are managed as sealed blobs stored in `/etc/blobs/`, and are only made available at runtime to the intended user under hardware-bound conditions. No secrets are persisted in plaintext on disk.

## Overview

- Secrets are sealed using a TPM 1.2 device and stored as binary blob files.
- At boot, a systemd unit runs a script to unseal each blob.
- The resulting secrets are written into:
  - `/run/<user>/env` – for systemd `EnvironmentFile=`
  - `/run/<user>/.env` – for shell or development sourcing
- Both files are owned by the user and stored in tmpfs (`/run`), not persisted across reboots.

## Use Cases

`tpm123` is intended for systems where storing secrets on disk (persistently) poses a risk — whether due to security constraints, threat models, or compliance goals, and where TPM 1.2 is available.

Example scenarios:

- Embedded or industrial Linux systems where full disk encryption is overkill, but runtime secrets are still required
- Long-lived servers or appliances with TPM 1.2 hardware and no TPM 2.0 upgrade path
- Air-gapped or offline systems where injecting secrets at runtime is impractical
- Development environments where secrets should exist only in memory and never touch disk
- Use with systemd units that require per-user secrets available early in the boot process

The tool is designed to be minimal, composable, and safe by default — secrets are hardware-bound, never written to disk in plaintext, and discarded at reboot.

## Blob File Format

Blob files must be located in `/etc/blobs/` and named with the following pattern:

```
/etc/blobs/<username>_<envarname>.blob
```

- The `<username>` must correspond to an existing local user.
- The `<envarname>` is converted to uppercase and sanitized into a valid environment variable name.

- Example: `/etc/blobs/alice_my_secret.blob`

## Behavior

- An existing zero-length blob is a request for a new random value. At startup, the script generates 256 random bytes, base64-encodes and seals them, then unseals the result into the runtime files.
- Nonempty blobs are unsealed without generating a replacement. Non-regular blobs cause failure.
- Sealed output is staged before replacing the empty blob. A failed seal leaves the empty request intact and reports its exit status without publishing runtime outputs.
- Missing blob files cannot be inferred from a directory scan. If no blobs exist, startup has nothing to unseal.
- A failed unseal logs the blob path and exit status, without logging the secret, and exits unsuccessfully. Runtime outputs are published only after all selected blobs unseal successfully; a failed rerun leaves previous outputs intact.
- As before, newlines are stripped from unsealed values. This is intended for text secrets, not arbitrary binary payloads.
- Shell and systemd output files use separate quoting rules so quotes and backslashes retain their values.
- The unsealed secret is written to both `/run/<user>/env` and `/run/<user>/.env` in the following formats:

```sh
# /run/<user>/env
MY_SECRET="base64encodedvalue"

# /run/<user>/.env
export MY_SECRET='base64encodedvalue'
```

## Systemd Integration

A sample systemd unit file is included: `tpm123.service`. It requires and starts after
`tcsd.service`, in addition to waiting for the TPM device. Waiting for the device
alone does not order the TPM userspace daemon before the unseal command. This fixes
the observed concurrent startup. The operator reported successful production
service restart and boot validation on 2026-10-16.

This is a one-shot task. After a successful run, `inactive (dead)` is normal;
check `Result=success` and `ExecMainStatus=0`. No automatic retry is configured:
a failed unseal should remain visible rather than conceal a persistent problem.

It is intended to run early at boot, before user services that may depend on the unsealed secrets.

To install:

1. Install `tpm123` into `/usr/local/sbin/` as a root-owned executable (mode `0755`)
2. Copy `tpm123.service` to `/etc/systemd/system/`
3. After replacing an existing unit, run `systemctl daemon-reload`. Enable the service:

```
#> systemctl enable tpm123.service
#> systemctl start tpm123
```

## Requesting a new random secret

Create a zero-length blob with the intended username and variable name. The next
startup or manual run of `tpm123` seals a random value there and publishes it:

```sh
install -d -o root -g root -m 0700 /etc/blobs
# Create a new request only; noclobber avoids truncating an existing secret.
(umask 077; set -C; : > /etc/blobs/alice_my_secret.blob)
systemctl start tpm123.service
```

Run these commands as root. The same generation occurs automatically at boot;
there is no separate creation command. Plaintext travels through pipes; only
sealed data is staged on disk. Once populated, the blob is reused on subsequent
runs. Back up sealed blobs according to the protected data's recovery needs.

The filename format splits at the first underscore, so usernames containing
underscores cannot be represented unambiguously.

## Local checks

```sh
bash -n tpm123
python3 -m unittest discover -s tests -v
```

Tests use temporary directories, synthetic values and mocked TPM tools. They do
not access a TPM, real blobs or runtime secrets. They cover failure status,
quoting, file modes, cleanup, preservation of old outputs, startup generation for
empty blobs, and reuse of populated blobs. These tests do not replace hardware
unsealing and boot validation on the target.

## Security Notes

- All secrets are sealed to the TPM and unsealed only under correct system state (PCR-bound if configured).
- Custom secret values can be created using tpm_sealdata, writing the blob to `/etc/blobs/` with the appropriate nomenclature, and will be automatically unsealed at boot like any other.
- Secrets are never written to disk unencrypted.
- Secrets exist only in `/run`, which is cleared on reboot.
- Output files are `chmod 400` and `chown <user>:<user>` by default.
- Uses the 'well-known' SRK password for `tpm_sealdata`.

## Requirements

- TPM 1.2 hardware
- `tpm_sealdata` and `tpm_unsealdata` (from `tpm-tools` / `trousers`)
- GNU `base64` with `--wrap=0` support
- Bash

## License

MIT
