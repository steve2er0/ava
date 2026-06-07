# References

This folder is AVA's controlled reference registry. It records the source IDs that knowledge artifacts may cite when they explain engineering theory, thresholds, rules, or assumptions.

## Citation Rule

Any AVA knowledge artifact that states engineering theory, rule rationale, acceptance logic, or a technical threshold must point to one or more IDs in `reference_index.json`.

If the source is not yet linked, the artifact must be marked `draft_reference_pending` and must use a placeholder reference. Placeholder references are allowed for starter knowledge, but they are not acceptable for approved or released engineering knowledge.

## Source Status

- `metadata_only`: official source record is available, but the underlying document is copyrighted or paywalled. Cite the document identity, but do not extract procedure text.
- `bibliographic_record`: a reliable bibliographic record exists, but full text has not been confirmed.
- `open_public`: public source material is available for ingestion and traceable extracts.
- `public_standard_copy`: a public copy of a standard method was found, but contractual use should still verify the latest official source.
- `draft_placeholder`: temporary internal marker for uncited starter knowledge.

## Response Behavior

When AVA cites theory, it should include the relevant reference IDs. If only placeholder references are available, AVA should say the statement is internal starter guidance and should not present it as an external authority.
