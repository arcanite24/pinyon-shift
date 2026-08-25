# Security policy

Please report a vulnerability privately through GitHub's **Report a
vulnerability** feature. Do not open a public issue containing exploit details,
private paths, credentials, dumps, or game content.

Only the latest tagged launcher release is supported. Portable dependency
archives are pinned and SHA-256 verified; the Microsoft installer must carry a
valid Microsoft Authenticode signature. A local native build necessarily
executes compilers and source obtained from the listed upstream projects. Review
`config/release-toolchain.json` and `patches/rexglue` before running setup if
your threat model requires it.
