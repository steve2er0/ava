# Acoustics and Vibration Reference Survey

Status: draft_reference_survey
Research date: 2026-06-07

This survey maps the initial AVA acoustics, vibroacoustics, random vibration, shock, and fatigue-damage references into source records that can be used by the knowledge base.

## Use Policy

- `metadata_only` sources identify official standards/books/articles but should not be mined for equations or procedure text unless licensed content is provided.
- `open_public` sources can be ingested into `raw/` and traced through `processed/` before extracts or rules are promoted.
- `bibliographic_record` sources are citation candidates; do not promote detailed claims until full text is available.
- Implementation references are useful for code behavior but do not override governing standards.

## Building Acoustics and Environmental Noise

| Source ID | Role | Use in AVA |
| --- | --- | --- |
| `REF-ASTM-E90-2023` | Governing ASTM laboratory airborne sound transmission-loss method | Identify the North American test method for lab TL/STC input data. Do not quote standard procedure text without licensed content. |
| `REF-ISO-10140-2-2021` | ISO airborne sound insulation measurement method | Use as the ISO airborne sound-insulation counterpart to ASTM E90. |
| `REF-ISO-10140-5-2021` | ISO facility and equipment requirements for sound insulation testing | Use to flag whether test facility/equipment validity is in scope. |
| `REF-ISO-1996-1-2016` | Environmental noise quantities and assessment procedures | Use for environmental-noise terminology, rating-level posture, and assessment scope. |
| `REF-ISO-1996-2-2017` | Environmental noise sound-pressure-level determination | Use when the workflow needs measurement procedure detail beyond ISO 1996-1. |
| `REF-ISO-9613-2-2024` | Outdoor sound propagation prediction method | Use as the current outdoor propagation reference. Treat 1996 material as historical unless the project invokes it. |
| `REF-MAEKAWA-1968` | Foundational barrier/screen diffraction paper | Use as a citation candidate for barrier insertion-loss concepts after full-text verification. |
| `REF-IEC-61260-1-2014` | Octave/fractional-octave filter specification | Use as the governing source for octave-band filter requirements. |
| `REF-ACOUSTIC-TOOLBOX-IEC-61260-1` | Open implementation reference | Use for Python implementation checks, not as the governing standard. |

## Vibroacoustic Theory References

| Source ID | Role | Use in AVA |
| --- | --- | --- |
| `REF-BERANEK-VER-2006` | General noise and vibration control textbook | Use for broad acoustics/noise-control theory after licensed text verification. |
| `REF-CREMER-HECKL-PETERSSON-2005` | Structure-borne sound textbook | Use for structural wave, mobility, damping, attenuation, and radiation theory after licensed text verification. |
| `REF-FAHY-GARDONIO-2007` | Vibroacoustic radiation/transmission/response textbook | Use for fluid-structure interaction, sound radiation, and transmission concepts after licensed text verification. |
| `REF-BENDAT-PIERSOL-2010` | Random data and spectral analysis textbook | Use for PSD, random data, spectral-estimation, and nonstationary-data theory after licensed text verification. |

## Random Vibration, FDS, and Damage-Based Testing

| Source ID | Role | Use in AVA |
| --- | --- | --- |
| `REF-HENDERSON-PIERSOL-1995` | Foundational damage-potential article | Citation candidate for random-vibration damage-potential concepts; full text still needed before extracting equations. |
| `REF-MCNEILL-2008` | Open FDS/FDET implementation paper | High-priority ingestion source for FDS/FDET concepts, assumptions, and example workflows. |
| `REF-ASTM-E1049-2017` | Cycle-counting practices | Governing reference for rainflow/cycle-counting method families; do not quote details without licensed content. |
| `REF-JANG-2020-FDS-PSD-SYNTHESIS` | Open modern FDS/PSD synthesis article | Useful implementation cross-check for FDS-based random PSD synthesis. |
| `REF-NASA-DBA-2017` | NASA damage-based assessment overview | Useful NASA-facing roadmap that connects McNeill, ISO 18431-4, ASTM E1049, and Bendat/Piersol. |

## Shock and Pyroshock

| Source ID | Role | Use in AVA |
| --- | --- | --- |
| `REF-SMALLWOOD-1980` | SRS recursive-filter algorithm reference | Algorithm citation candidate. Use ISO 18431-4 for formal standard posture. |
| `REF-ISO-18431-4-2007` | SRS signal-processing standard | Use as the governing SRS digital-calculation reference. |
| `REF-IRVINE-VRS-2009` | Open vibration response spectrum tutorial | Useful teaching and implementation source for VRS workflows. |
| `REF-IRVINE-SRS-2023` | Open shock/vibration response spectra tutorial | Useful broad tutorial source; not governing. |
| `REF-MIL-STD-810G-METHOD-517-2008` | MIL-STD-810G pyroshock method | Use for G-revision Method 517 context when a project invokes MIL-STD-810G. |
| `REF-MIL-STD-810H-METHOD-517-2019` | MIL-STD-810H pyroshock method | Use as a current-revision comparison source; verify official status through ASSIST/DLA for compliance. |
| `REF-NASA-STD-7003A-2011` | NASA pyroshock test criteria | High-priority ingestion source for NASA pyroshock criteria and margins. Verify whether a program invokes a newer revision. |

## Aerospace Vibroacoustic Criteria

| Source ID | Role | Use in AVA |
| --- | --- | --- |
| `REF-NASA-HDBK-7005-2001` | NASA dynamic environmental criteria handbook | High-priority ingestion source for launch/space dynamic-environment taxonomy and criteria development posture. |
| `REF-NASA-TM-2009-215902` | Saturn V/Titan III vibroacoustic databank update | High-priority ingestion source for random vibration criteria development from vibroacoustic databanks. |
| `REF-NASA-TP-1998-1982` | Historical computerized vibroacoustic databank publication | Supporting source for databank methodology and historical context. |

## Recommended Ingestion Order

1. `REF-MCNEILL-2008`, `REF-NASA-TM-2009-215902`, and `REF-NASA-STD-7003A-2011` because they are open, directly useful, and can seed FDS/random-vibration/pyroshock workflows.
2. `REF-NASA-HDBK-7005-2001`, `REF-IRVINE-VRS-2009`, and `REF-NASA-DBA-2017` because they fill dynamic-environment taxonomy and response-spectrum support.
3. Standards metadata records for ASTM/ISO/IEC so AVA can cite governing document IDs without extracting copyrighted procedure text.
4. Book metadata records for Beranek/Ver, Cremer/Heckl/Petersson, Fahy/Gardonio, and Bendat/Piersol; promote theory extracts only after licensed excerpts or user-provided notes are available.

## Gaps

- Full text is not currently linked for `REF-HENDERSON-PIERSOL-1995` or `REF-SMALLWOOD-1980`; only bibliographic records were found.
- ISO, IEC, ASTM, Wiley, Springer, Elsevier, and Academic Press sources are primarily official metadata records unless the user provides licensed access.
- NASA-STD-7003B is referenced by NASA public articles, but this survey registers NASA-STD-7003A because an accessible NASA-hosted PDF was found. Add 7003B only after locating a stable source record or project-provided copy.
