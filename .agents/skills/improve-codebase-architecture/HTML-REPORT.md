# Architecture Report

Create one HTML file with inline CSS and SVG and no external fonts, scripts, or CDN dependencies.
Use semantic headings, a readable maximum width, high contrast, and a responsive two-column before/after layout that stacks on narrow screens.
Escape repository text before inserting it into HTML.
Do not embed credentials, private request payloads, or executable application source.

## Contents

Start with the project, review scope, date, and inspected revision or working-tree context.
For every candidate, show exact file paths and caller evidence, the current problem, proposed responsibility change, benefits, risks, and confidence.
Use the strength labels Strong, Worth exploring, and Speculative.
Link report sections with ordinary anchors.

Draw before/after diagrams with inline SVG or styled HTML boxes.
Label every relationship and distinguish current structure from a proposed design.
Use solid boxes for modules and dashed lines for test seams.
Do not use implementation size as a numerical proxy for design quality.

End with a top recommendation linked to its candidate card, or explain why no worthwhile candidate was established.
State what was inspected and what remains uncertain.
Use the project's domain names and the vocabulary in [codebase-design](../codebase-design/SKILL.md).

## Delivery and verification

Resolve the OS temporary directory with the host's native facilities, such as System.IO.Path.GetTempPath on Windows.
Write a fresh architecture-review-TIMESTAMP.html file, or use an approved artifact directory.
Use an available preview tool to open it and provide an absolute clickable path.
When browser inspection is available, verify readable diagrams, narrow-screen layout, and absence of missing assets.
If rendering cannot be inspected, report that limitation.
