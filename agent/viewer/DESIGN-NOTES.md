# Site Safety Watch console design notes

Research performed on 2026-10-03. References are used for interaction and information patterns
only. No assets, logos, icons, fonts or brand treatments were copied.

## References

| Reference | URL | Borrow | Avoid |
|---|---|---|---|
| Verkada Command alerts | https://help.verkada.com/command/organization-settings/create-alerts-across-verkada-products/manage-alerts-across-verkada-products | Event-first navigation, site and location metadata, direct link from alert to footage | Configuration controls and product-wide navigation that compete with the incident |
| Verkada Command platform | https://www.verkada.com/command/ | Associated video context beside actionable alerts | Large multi-camera mosaics that make the important feed too small |
| Samsara dashboard menus | https://kb.samsara.com/hc/en-us/articles/48621492984589-Dashboard-Menus | Clear separation between live overview, safety events and incident center | Broad suite navigation and unrelated fleet modules |
| Samsara safety dashboard | https://kb.samsara.com/hc/en-us/articles/20287494189709-View-your-Safety-Dashboard-from-the-Driver-Portal | Time, asset and event type as the core event row | Historical scorecards in the live response view |
| Voxel customer workflow | https://www.voxelai.com/customer-stories/carlex | Evidence footage as a coaching artifact and transparent audit material | Marketing claims or outcome numbers not measured by this build |
| Protex AI platform | https://www.protex.ai/ | Event-level evidence, site context and privacy controls | Heatmaps, trend reports and multi-site analytics outside the demo path |
| PagerDuty incidents | https://docs.pagerduty.com/incident-management/incidents/overview | Explicit triggered, acknowledged and resolved state; chronological incident history | Dense responder controls because decisions happen in Slack |
| Datadog incident timeline | https://docs.datadoghq.com/incident_response/incident_management/investigate/timeline/ | Each state change records what happened, who acted and when | Tabs, graphs and editable notes that imply unsupported capabilities |
| Linear My Issues | https://linear.app/docs/my-issues | Compact rows, selected-row clarity and meaningful focus order | Productive-work controls in a read-only monitoring surface |

## Chosen direction: evidence docket

```text
+ identity and verified live state ------------------------------------------+
| dominant evidence plate                         | chronological event rail |
| camera replay or newest frame                   | newest event first       |
| active hazard stamp                             | status in every row      |
+ selected evidence record -----------------------+--------------------------+
| model observation | stored rule | proposed fix | disposition timeline      |
+ measured GB10 values, only when numbers.json exists -----------------------+
```

- Matte carbon surfaces and ruled evidence sections, not floating dashboard cards.
- Hazard orange marks unresolved evidence; resolved teal marks approved events.
- Warm off-white carries primary text; blue-grey carries secondary metadata.
- System sans: 12 px metadata, 14 px body, 18 px panel headings, 32 px hazard stamp.
- Tabular numbers for time and confidence.
- New evidence enters once with a clipped reveal and brief highlight.
- Polling never animates unchanged rows; reduced-motion removes the reveal.
- At narrow widths the event rail follows the evidence plate, preserving reading order.
- Direction seed: 18af7262. The evidence docket beat vertical-media and split-flap challengers
  on product clarity and EHS identification because it keeps footage, event state and audit
  history visible together.
