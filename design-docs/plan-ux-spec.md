# Migration Plan Feature -- UX Specification

**Date:** 2026-03-18
**Status:** Draft
**Author:** Product Design

---

## Table of Contents

1. [User Flow](#1-user-flow)
2. [Dashboard Enhancement](#2-dashboard-enhancement)
3. [Plan Review Modal](#3-plan-review-modal)
4. [MigrationPlan Page](#4-migrationplan-page)
5. [WorkloadDetail Page](#5-workloaddetail-page)
6. [Design Tokens](#6-design-tokens)
7. [Component Hierarchy](#7-component-hierarchy)
8. [Interaction States](#8-interaction-states)
9. [Accessibility Notes](#9-accessibility-notes)
10. [New Routes & Navigation](#10-new-routes--navigation)

---

## 1. User Flow

### Primary Journey: End-to-End Migration Plan

```
  Dashboard                       Plan Review               MigrationPlan Page
  (migration card)                (modal overlay)           /plans/:planId
  +------------------+           +------------------+      +------------------+
  | Migration "Acme" |           | Plan Summary     |      | Phase Timeline   |
  | 47 resources     |           | 47 resources     |      | [=====--------]  |
  | [Generate Plan]--+---------->| 5 phases         |      |                  |
  +------------------+   POST    | 7 workloads      |      | Phase 1: Network |
                         /api/   |                  |      |   [ ] VPC wkld   |
                         migr./  | Phase list:      |      | Phase 2: Data    |
                         {id}/   |  1. Networking   |      |   [ ] RDS wkld   |
                         plan    |  2. Data Layer   |      | ...              |
                                 |  3. App Layer    |      +--------+---------+
                                 |  4. Traffic Mgmt |               |
                                 |  5. IAM          |               | click workload
                                 |                  |               v
                                 | [Discard] [Open]-+---->  WorkloadDetail Page
                                 +------------------+       /workloads/:workloadId
                                                           +------------------+
                                                           | VPC Translation  |
                                                           | 3 resources      |
                                                           | [Execute]        |
                                                           +--------+---------+
                                                                    |
                                                             POST /api/
                                                             workloads/{id}/
                                                             execute
                                                                    |
                                                                    v
                                                           +------------------+
                                                           | SSE Progress     |
                                                           | (reuse           |
                                                           |  SkillProgress   |
                                                           |  Tracker)        |
                                                           +--------+---------+
                                                                    |
                                                                    v
                                                           +------------------+
                                                           | Results Tab      |
                                                           | (reuse           |
                                                           |  ArtifactViewer) |
                                                           +------------------+
```

### Step-by-Step Narrative

| Step | User Action | System Response | Endpoint |
|------|-------------|-----------------|----------|
| 1 | User navigates to Dashboard | Dashboard loads migrations with resource counts | GET /api/migrations |
| 2 | User clicks "Generate Plan" on a migration card | Loading spinner replaces button; POST fires | POST /api/migrations/{id}/plan |
| 3 | Plan generation completes | **Plan Review Modal** appears with plan summary | Response from POST |
| 4a | User clicks "Open Plan" | Navigate to /plans/{planId} | -- |
| 4b | User clicks "Discard Plan" | Confirm dialog; DELETE plan; modal closes | DELETE /api/plans/{id} |
| 5 | On MigrationPlan page, user reviews phases | Phases rendered as vertical timeline with status badges | GET /api/plans/{id} |
| 6 | User expands a phase | Workload cards slide open within that phase | -- (client-side) |
| 7 | User clicks a workload card | Navigate to /workloads/{workloadId} | -- |
| 8 | On WorkloadDetail, user clicks "Execute" | Confirm dialog; button becomes spinner; SSE stream opens | POST /api/workloads/{id}/execute |
| 9 | SSE events stream in | SkillProgressTracker shows live progress | GET /api/workloads/{id}/execute/stream (via skill_run SSE) |
| 10 | Execution completes | Tabs switch to show Results + Artifacts | GET /api/skill-runs/{id}, /artifacts |
| 11 | User returns to plan page | Workload card shows "completed" badge; phase progress updates | GET /api/plans/{id}/status |

### Phase Dependency Rule

Phases are sequentially dependent. The UI enforces this:

- Phase N+1 workloads show "Execute" buttons only when ALL workloads in Phase N have status "complete".
- If Phase N has any "failed" workloads, Phase N+1 workloads show a disabled "Blocked" state with a tooltip: "Complete Phase N first".
- Phase 1 workloads are always executable (no prior dependency).
- Within a single phase, workloads can be executed in parallel (no intra-phase ordering).

### Plan Regeneration Flow

If a plan already exists for a migration:
- The Dashboard button reads "View Plan" (primary) with a small "Regenerate" link below.
- Clicking "Regenerate" shows a confirmation: "This will discard the current plan and all workload progress. Continue?"
- On confirm: DELETE old plan, POST new plan, show Review Modal.

---

## 2. Dashboard Enhancement

### Current State (Dashboard.tsx)

The Dashboard currently shows three count cards (Resources, Skill Runs, Migrations) and a "Recent Skill Runs" table. Migrations link to /resources.

### New Design: Migration Cards Section

Add a new section below the count cards and above "Recent Skill Runs" titled "Migrations". Each migration gets its own card.

```
+------------------------------------------------------------------------+
| Dashboard                                                               |
| Overview of your AWS to OCI migration progress.                         |
+------------------------------------------------------------------------+

+-------------------+  +-------------------+  +-------------------+
| [server icon]     |  | [bolt icon]       |  | [cycle icon]      |
| Resources         |  | Skill Runs        |  | Migrations        |
| 47                |  | 12                |  | 2                 |
+-------------------+  +-------------------+  +-------------------+

[ New Skill Run ]  [ Manage Connections ]

+------------------------------------------------------------------------+
| Migrations                                                              |
+------------------------------------------------------------------------+
|                                                                         |
| +----------------------------------+  +-------------------------------+ |
| | Acme Corp Migration              |  | Dev Environment               | |
| | Created Mar 15, 2026             |  | Created Mar 12, 2026          | |
| |                                  |  |                               | |
| | 47 resources discovered          |  | 8 resources discovered        | |
| | [AWS::EC2::VPC] [AWS::RDS::...]  |  | [AWS::EC2::Instance] [...]    | |
| |                                  |  |                               | |
| | Plan: Active (3/5 phases done)   |  | No plan generated             | |
| | [####============] 60%           |  |                               | |
| |                                  |  |                               | |
| | [View Plan]  Regenerate          |  | [Generate Plan]               | |
| +----------------------------------+  +-------------------------------+ |
|                                                                         |
+------------------------------------------------------------------------+

+------------------------------------------------------------------------+
| Recent Skill Runs                                     (existing table)  |
+------------------------------------------------------------------------+
```

### Migration Card Spec

```
+----------------------------------------------------+
| migration.name                          status-dot  |
| "Created " + formatDate(migration.created_at)       |
|                                                     |
| {resource_count} resources discovered               |
| [type-chip] [type-chip] [type-chip] +N more         |
|                                                     |
| -- If no plan: -----------------------------------  |
| [ Generate Plan ]  (blue primary button)            |
|                                                     |
| -- If plan exists, status=draft: -----------------  |
| Plan generated (draft)                              |
| [ Review Plan ]  Regenerate                         |
|                                                     |
| -- If plan exists, status=active: ----------------  |
| Plan: {completed}/{total} phases complete           |
| [=========---------] {percent}%                     |
| [ View Plan ]  Regenerate                           |
|                                                     |
| -- If plan status=complete: ----------------------  |
| Plan: Complete (checkmark icon)                     |
| [ View Plan ]                                       |
|                                                     |
| -- If plan status=failed: ------------------------  |
| Plan: Failed (x icon, red text)                     |
| [ View Plan ]  Regenerate                           |
+----------------------------------------------------+
```

### Card Layout CSS

- Container: `grid grid-cols-1 md:grid-cols-2 gap-6`
- Card: `bg-white rounded-lg shadow p-6 space-y-3`
- Title: `text-lg font-semibold text-gray-900`
- Date: `text-sm text-gray-500`
- Resource count: `text-sm text-gray-700 font-medium`
- Type chips: `inline-flex px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs font-mono`
- Progress bar container: `w-full h-2 bg-gray-200 rounded-full overflow-hidden`
- Progress bar fill: `h-full bg-blue-500 rounded-full transition-all duration-500`
- "Generate Plan" button: same style as existing "New Skill Run" button (`px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium`)
- "Regenerate" link: `text-sm text-gray-500 hover:text-gray-700 underline ml-3`
- "View Plan" button: same primary button style

### Generate Plan Button States

| State | Appearance | Behavior |
|-------|-----------|----------|
| Default | Blue primary button, "Generate Plan" | Clickable |
| Hover | Darker blue bg (`hover:bg-blue-700`) | Cursor pointer |
| Loading | "Generating..." with spinner icon, `opacity-75 cursor-not-allowed` | Disabled |
| Error | Button reappears; red error banner above card | Shows error message from API |
| No resources | Button disabled, tooltip "Discover resources first" | `opacity-50 cursor-not-allowed` |

---

## 3. Plan Review Modal

This is the critical "review step" that the architect identified as missing. When a plan is generated, instead of navigating immediately, a modal overlay appears so the user can review before committing.

### Wireframe

```
+======================================================================+
| (dark overlay behind)                                                 |
|                                                                       |
|   +--------------------------------------------------------------+   |
|   | Migration Plan Generated                              [X]    |   |
|   |--------------------------------------------------------------|   |
|   |                                                              |   |
|   |  Summary                                                     |   |
|   |  ---------                                                   |   |
|   |  Migration:       Acme Corp Migration                        |   |
|   |  Total Resources: 47                                         |   |
|   |  Phases:          5                                          |   |
|   |  Generated:       Mar 18, 2026 at 3:42 PM                   |   |
|   |                                                              |   |
|   |  Resource Breakdown                                          |   |
|   |  --------------------                                        |   |
|   |  AWS::EC2::VPC .......................... 3                   |   |
|   |  AWS::RDS::DBInstance ................... 5                   |   |
|   |  AWS::EC2::Instance .................... 12                   |   |
|   |  AWS::ElasticLoadBalancingV2 ............ 4                   |   |
|   |  AWS::IAM::Policy ...................... 23                   |   |
|   |                                                              |   |
|   |  Phases                                                      |   |
|   |  ------                                                      |   |
|   |  1. Networking Foundation     3 resources   network_transl.  |   |
|   |  2. Data Layer                5 resources   database_transl. |   |
|   |  3. Application Layer        12 resources   ec2_translation  |   |
|   |  4. Traffic Management        4 resources   loadbalancer_t.  |   |
|   |  5. Identity & Access        23 resources   iam_translation  |   |
|   |                                                              |   |
|   |  (i) Phases must be executed in order. Phase 2               |   |
|   |      cannot start until Phase 1 is complete.                 |   |
|   |                                                              |   |
|   |  +---------------------+  +-------------------+             |   |
|   |  | Discard Plan        |  | Open Plan  ->     |             |   |
|   |  | (outlined, gray)    |  | (filled, blue)    |             |   |
|   |  +---------------------+  +-------------------+             |   |
|   |                                                              |   |
|   +--------------------------------------------------------------+   |
|                                                                       |
+======================================================================+
```

### Modal Spec

- Overlay: `fixed inset-0 z-50 flex items-start justify-center bg-black/50 overflow-y-auto py-8 px-4` (matches existing ArtifactViewer modal pattern)
- Modal container: `bg-white rounded-xl shadow-2xl w-full max-w-2xl`
- Header: `flex items-center justify-between px-6 py-4 border-b border-gray-200`
  - Title: `text-xl font-bold text-gray-900` -- "Migration Plan Generated"
  - Close button: `w-8 h-8 flex items-center justify-center rounded-full hover:bg-gray-100 text-gray-500`
- Body: `px-6 py-6 space-y-6`
- Summary grid: `grid grid-cols-2 gap-4 text-sm`
  - Label: `text-gray-500`
  - Value: `font-medium text-gray-900`
- Resource breakdown: `space-y-1` with each row as `flex justify-between text-sm`
  - Type: `font-mono text-gray-700`
  - Count: `font-medium text-gray-900`
- Phase list: numbered list, each item as `flex items-center gap-4 text-sm py-2 border-b border-gray-50`
  - Number: `w-6 h-6 rounded-full bg-gray-100 text-gray-600 text-xs font-bold flex items-center justify-center flex-shrink-0`
  - Name: `font-medium text-gray-900 flex-1`
  - Resource count: `text-gray-500`
  - Skill type: `font-mono text-xs text-gray-400`
- Info banner: `flex gap-3 p-3 bg-blue-50 rounded-lg text-sm text-blue-700`
  - Icon: info circle (i)
- Footer: `px-6 py-4 border-t border-gray-200 flex justify-end gap-3`
  - "Discard Plan": `px-4 py-2 bg-white text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-50 font-medium`
  - "Open Plan": `px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium`

### Discard Behavior

- Clicking "Discard Plan" shows a browser `confirm()` dialog: "Are you sure? This will delete the generated plan."
- On confirm: calls DELETE /api/plans/{id}, closes modal, shows toast "Plan discarded".
- On cancel: modal stays open.

---

## 4. MigrationPlan Page

**Route:** `/plans/:planId`

This is the primary plan management page. It shows the plan overview at the top and phases in a vertical timeline below.

### Overall Layout Wireframe

```
+------------------------------------------------------------------------+
| <- Back to Dashboard                                                    |
|                                                                         |
| Migration Plan                                          [Delete Plan]   |
| Acme Corp Migration  *  Draft                                           |
| Generated Mar 18, 2026 at 3:42 PM                                      |
+------------------------------------------------------------------------+

+-------------------+  +------------------+  +------------------+
| Total Resources   |  | Phases           |  | Completion       |
| 47                |  | 5                |  | 0%               |
| across 5 types    |  | 2 pending        |  | [===-----------] |
|                   |  | 0 in progress    |  | 0/5 phases done  |
+-------------------+  +------------------+  +------------------+

+------------------------------------------------------------------------+
| Phase Timeline                                                          |
+------------------------------------------------------------------------+
|                                                                         |
|  (1)----(2)----(3)----(4)----(5)                                       |
|  [*]    [ ]    [ ]    [ ]    [ ]                                       |
|  Net    Data   App    Traf   IAM                                       |
|                                                                         |
+------------------------------------------------------------------------+

+------------------------------------------------------------------------+
| Phase 1: Networking Foundation                    PENDING               |
| Translate VPCs, subnets, and security groups      3 resources           |
| to OCI VCNs.                                      1 workload            |
|------------------------------------------------------------------------|
| v  (expanded by default for first actionable phase)                    |
|                                                                         |
|  +------------------------------------------------------------------+  |
|  | Networking Foundation workload             network_translation    |  |
|  | Migrate 3 resource(s): AWS::EC2::VPC                             |  |
|  | Resources: 3                                                     |  |
|  |                                          [ Execute ]             |  |
|  +------------------------------------------------------------------+  |
|                                                                         |
+------------------------------------------------------------------------+

+------------------------------------------------------------------------+
| Phase 2: Data Layer                               PENDING  (locked)     |
| Translate RDS instances to OCI database           5 resources           |
| services.                                         1 workload            |
|------------------------------------------------------------------------|
| >  (collapsed; locked because Phase 1 not complete)                    |
+------------------------------------------------------------------------+

+------------------------------------------------------------------------+
| Phase 3: Application Layer                        PENDING  (locked)     |
| ...                                                                     |
+------------------------------------------------------------------------+

(etc.)
```

### Summary Stats Row

Three stat cards in a `grid grid-cols-1 md:grid-cols-3 gap-6`:

**Card 1 -- Total Resources**
- Label: `text-xs font-medium text-gray-400 uppercase tracking-wider` -- "Total Resources"
- Value: `text-3xl font-bold text-gray-900` -- plan.summary.total_resources
- Subtitle: `text-sm text-gray-500` -- "across {N} types"

**Card 2 -- Phases**
- Label: "Phases"
- Value: total phase count
- Subtitle: "{N} pending, {N} in progress" (derived from phase statuses)

**Card 3 -- Completion**
- Label: "Completion"
- Value: percentage (completed phases / total phases, rounded)
- Progress bar: `w-full h-2 bg-gray-200 rounded-full mt-2`
  - Fill: `h-full rounded-full transition-all duration-700` with color based on status:
    - All complete: `bg-green-500`
    - Has failures: `bg-red-500`
    - In progress: `bg-blue-500`
    - All pending: `bg-gray-300`
- Subtitle: "{completed}/{total} phases done"

### Phase Timeline Bar

A horizontal connected-dot visualization above the phase accordion. Sits inside a `bg-white rounded-xl shadow-sm border border-gray-100 p-6` card.

```
  (1)---------(2)---------(3)---------(4)---------(5)
  [*]         [ ]         [ ]         [ ]         [ ]
  Networking  Data        App         Traffic     IAM
```

Each node:
- Circle: `w-10 h-10 rounded-full flex items-center justify-center`
  - Completed: `bg-green-100 text-green-600` with checkmark icon
  - Running: `bg-blue-100 text-blue-600 ring-2 ring-blue-400 ring-offset-2` with spinner
  - Failed: `bg-red-100 text-red-600` with X icon
  - Pending (unlocked): `bg-gray-100 text-gray-500` with phase number
  - Pending (locked): `bg-gray-50 text-gray-300` with lock icon
- Connector line between nodes:
  - Completed segment: `bg-green-400`
  - Incomplete segment: `bg-gray-200`
- Label below: `text-xs mt-1.5 font-medium text-center` with color matching status

This follows the exact same pattern as the existing SkillProgressTracker pipeline component.

### Phase Accordion Sections

Each phase is rendered as a collapsible section. Layout:

```
+------------------------------------------------------------------------+
|  [expand/collapse chevron]                                              |
|                                                                         |
|  Phase {order_index}: {name}                         [STATUS BADGE]     |
|  {description}                                       {N} resources      |
|                                                      {N} workload(s)    |
|------------------------------------------------------------------------|
|  (expanded content -- workload cards)                                   |
|                                                                         |
|  +------------------------------------------------------------------+  |
|  | {workload.name}                        {workload.skill_type}     |  |
|  | {workload.description}                                           |  |
|  |                                                                  |  |
|  | Resources: {resource_count}                                      |  |
|  |                                                                  |  |
|  | -- Status-dependent action area (see below) --                   |  |
|  +------------------------------------------------------------------+  |
|                                                                         |
+------------------------------------------------------------------------+
```

**Phase Section Container:**
- Outer: `bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden`
- Margin between sections: `space-y-4`

**Phase Header (clickable to expand/collapse):**
- Container: `flex items-start justify-between p-5 cursor-pointer hover:bg-gray-50 transition-colors`
- Left side:
  - Phase label: `text-base font-semibold text-gray-900` -- "Phase {N}: {name}"
  - Description: `text-sm text-gray-500 mt-1`
- Right side (stacked vertically, right-aligned):
  - Status badge (see Design Tokens section)
  - Resource count: `text-xs text-gray-400 mt-1` -- "{N} resources"
  - Workload count: `text-xs text-gray-400` -- "{N} workload(s)"
- Chevron icon: `w-5 h-5 text-gray-400 transition-transform` -- rotates 90deg when expanded

**Phase Header -- Locked State:**
- When the previous phase is not complete, the phase header shows a lock icon and the description includes "(Requires Phase {N-1} to complete first)".
- The header has reduced opacity: `opacity-60`
- Still expandable (user can see what is coming) but workload Execute buttons are disabled.

**Phase Expanded Content:**
- Container: `border-t border-gray-200 px-5 py-4 bg-gray-50`
- Workload cards listed inside.

### Workload Card

```
+------------------------------------------------------------------+
| [skill-type icon]  {workload.name}          [skill_type chip]    |
|                    {workload.description}                         |
|                                                                   |
|  Resources: {resource_count}                                      |
|                                                                   |
| (status-dependent action area)                                    |
+------------------------------------------------------------------+
```

**Card Container:**
- `bg-white rounded-lg border border-gray-200 p-4 hover:border-gray-300 transition-colors`
- If status == running: `border-blue-300 bg-blue-50/30`
- If status == complete: `border-green-300 bg-green-50/30`
- If status == failed: `border-red-300 bg-red-50/30`

**Skill Type Chip:**
- `inline-flex px-2 py-0.5 rounded text-xs font-mono font-medium`
- Colors per skill type:
  - network_translation: `bg-cyan-100 text-cyan-800`
  - database_translation: `bg-amber-100 text-amber-800`
  - ec2_translation: `bg-purple-100 text-purple-800`
  - loadbalancer_translation: `bg-indigo-100 text-indigo-800`
  - cfn_terraform: `bg-teal-100 text-teal-800`
  - iam_translation: `bg-orange-100 text-orange-800`
  - null/unknown: `bg-gray-100 text-gray-600`

**Status-Dependent Action Area (bottom of card):**

| Workload Status | Phase Unlocked? | Renders |
|-----------------|-----------------|---------|
| pending | Yes | `[ Execute ]` primary button |
| pending | No (prior phase incomplete) | `[ Blocked ]` disabled button + tooltip |
| running | -- | Mini progress bar + "Running..." text + `[ View Progress ]` link |
| complete | -- | Green checkmark + "Complete" + `[ View Results ]` link |
| failed | -- | Red X + error summary + `[ Retry ]` button + `[ View Details ]` link |

**Execute Button:**
- Same style as existing "Launch Skill Run": `px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm`
- On click: show confirm dialog "Execute this workload? This will translate {N} AWS resources using the {skill_type} skill."
- While executing POST: button shows "Starting..." with spinner, disabled

**View Progress Link:**
- `text-sm text-blue-600 hover:text-blue-800 font-medium`
- Navigates to /workloads/{workloadId}

**View Results Link:**
- `text-sm text-green-600 hover:text-green-800 font-medium`
- Navigates to /workloads/{workloadId}

**Retry Button:**
- `px-3 py-1.5 bg-red-50 text-red-700 border border-red-200 rounded-lg hover:bg-red-100 text-sm font-medium`
- On click: calls POST /api/workloads/{id}/execute (same as Execute -- the backend handles re-execution)

### "Execute All" Phase Action

When a phase is unlocked and all its workloads are pending, show a phase-level action:

```
  [ Execute All Workloads in Phase ]
```

- `px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm`
- Positioned at the bottom of the expanded phase content
- On click: confirm dialog, then sequentially POST execute for each workload in the phase
- Disabled if any workload in the phase is already running

### Delete Plan

- Top-right of the page header: `text-sm text-red-500 hover:text-red-700 font-medium`
- On click: `confirm("Delete this plan? All workload progress will be lost.")`
- On confirm: DELETE /api/plans/{id}, navigate to /dashboard

### Polling

- The MigrationPlan page should poll GET /api/plans/{planId}/status every 3 seconds while any workload has status "running".
- When polling detects all workloads are complete or failed, stop polling.
- Use the same `refetchInterval` pattern from `useSkillRun`:
  ```
  refetchInterval: (query) => {
    const plan = query.state.data;
    if (plan && (plan.status === 'complete' || plan.status === 'failed')) return false;
    if (plan?.phases?.some(p => p.status === 'running')) return 3000;
    return false;
  }
  ```

---

## 5. WorkloadDetail Page

**Route:** `/workloads/:workloadId`

This page shows a single workload in detail with three tabs: Overview, Progress, Results.

### Layout Wireframe

```
+------------------------------------------------------------------------+
| <- Back to Plan                                                         |
|                                                                         |
| Networking Foundation workload                          [STATUS BADGE]  |
| Phase 1: Networking Foundation                                          |
| network_translation  *  3 resources                                     |
+------------------------------------------------------------------------+

+--------+  +----------+  +----------+
| Overview|  | Progress |  | Results  |
+--------+  +----------+  +----------+

=== OVERVIEW TAB ===

+------------------------------------------------------------------------+
| Workload Details                                                        |
+------------------------------------------------------------------------+
| Skill Type:    network_translation                                      |
| Description:   Migrate 3 resource(s): AWS::EC2::VPC                     |
| Status:        Pending                                                  |
| Phase:         1 - Networking Foundation                                 |
+------------------------------------------------------------------------+

+------------------------------------------------------------------------+
| Included Resources (3)                                                  |
+------------------------------------------------------------------------+
| Type                  | Name            | ARN                  | Status |
|-----------------------|-----------------|-----------------------|--------|
| AWS::EC2::VPC         | prod-vpc        | arn:aws:ec2:us-e...  | disc.  |
| AWS::EC2::VPC         | staging-vpc     | arn:aws:ec2:us-e...  | disc.  |
| AWS::EC2::VPC         | dev-vpc         | arn:aws:ec2:us-e...  | disc.  |
+------------------------------------------------------------------------+

+----------------------------+
| [ Execute Workload ]       |    (or status-appropriate action)
+----------------------------+

=== PROGRESS TAB (visible when status == running) ===

+------------------------------------------------------------------------+
| (Reuses SkillProgressTracker component)                                 |
| skillRunId = workload.skill_run_id                                      |
|                                                                         |
| [Header card with skill type + run ID]                                  |
| [Confidence ring] [Iteration counter] [Elapsed timer]                   |
| [Phase pipeline: Gap Analysis -> Enhancement -> Review -> Fix -> Done]  |
| [Agent log table with live SSE updates]                                 |
+------------------------------------------------------------------------+

=== RESULTS TAB (visible when status == complete or failed) ===

+------------------------------------------------------------------------+
| Summary                                                                 |
+------------------------------------------------------------------------+
| Confidence:  87%           Cost: $0.0342           Duration: 2m 14s     |
| Iterations:  2             Started: 3:42 PM        Completed: 3:44 PM  |
+------------------------------------------------------------------------+

+------------------------------------------------------------------------+
| (Reuses ArtifactViewer component)                                       |
| skillRunId = workload.skill_run_id                                      |
|                                                                         |
| [terraform_tf]  main.tf              [View] [Download]                  |
| [run_report_md] translation_report   [Preview] [Download]               |
+------------------------------------------------------------------------+

+------------------------------------------------------------------------+
| Errors (only shown if status == failed)                                 |
+------------------------------------------------------------------------+
| <pre>{JSON.stringify(skillRun.errors)}</pre>                            |
|                                                                         |
| [ Retry Execution ]                                                     |
+------------------------------------------------------------------------+
```

### Tab Behavior

| Tab | Visible When | Content |
|-----|-------------|---------|
| Overview | Always | Workload metadata + resource table + action button |
| Progress | skill_run_id exists AND status is "running" | SkillProgressTracker with live SSE |
| Results | skill_run_id exists AND status is "complete" or "failed" | Summary stats + ArtifactViewer + error panel |

**Default tab selection:**
- If workload.status == "pending": Overview tab
- If workload.status == "running": Progress tab
- If workload.status == "complete" or "failed": Results tab

### Tab Navigation

Reuse the exact tab pattern from SkillRunResults.tsx:

```
<div className="border-b border-gray-200">
  <nav className="-mb-px flex gap-6">
    {TABS.map(tab => (
      <button className={cn(
        'py-3 px-1 text-sm font-medium border-b-2 transition-colors',
        active ? 'border-blue-500 text-blue-600'
               : 'border-transparent text-gray-500 hover:text-gray-700'
      )}>
        {tab.label}
      </button>
    ))}
  </nav>
</div>
```

### Resource Table

Reuse the existing `ResourceTable` component. If it does not support a read-only mode (no selection), add an optional `selectable={false}` prop that hides the radio/checkbox column.

Columns for the workload resource table:
- Type (`aws_type`): `font-mono text-sm`
- Name (`name`): `text-sm font-medium`
- ARN (`aws_arn`): `font-mono text-xs text-gray-500 truncate max-w-[240px]`
- Status (`status`): status badge

### Execute Button on Overview Tab

Same logic as the workload card on the MigrationPlan page:

| Condition | Button |
|-----------|--------|
| status=pending, phase unlocked | `[ Execute Workload ]` primary blue |
| status=pending, phase locked | `[ Blocked: Complete Phase {N-1} first ]` disabled gray |
| status=running | `Execution in progress... View the Progress tab` (text, no button) |
| status=complete | `Execution complete. View the Results tab.` (text, no button) |
| status=failed | `[ Retry Execution ]` red-outlined button |

### SSE Progress Integration

When the user executes a workload from this page:
1. POST /api/workloads/{id}/execute returns `{ skill_run_id: "..." }`
2. Automatically switch to the Progress tab
3. Render `<SkillProgressTracker skillRunId={skillRunId} onComplete={handleComplete} />`
4. `handleComplete` switches to the Results tab and refreshes workload data

This is the exact same pattern used by the existing SkillRunProgress page.

### Back Navigation

- "Back to Plan" link at top-left
- Stores the plan ID from the URL query param or from workload data
- Route: `/plans/{planId}`

---

## 6. Design Tokens

### Status Colors

Consistent across all plan, phase, and workload statuses. These align with the existing `statusColors` in Dashboard.tsx and `StatusBadge` in SkillProgressTracker.tsx.

| Status | Badge BG + Text | Dot Color | Border Accent | Icon |
|--------|----------------|-----------|---------------|------|
| pending | `bg-gray-100 text-gray-700` | `bg-gray-400` | `border-gray-200` | Clock/circle outline |
| draft | `bg-gray-100 text-gray-700` | `bg-gray-400` | `border-gray-200` | Document outline |
| running | `bg-blue-100 text-blue-700` | `bg-blue-500 animate-pulse` | `border-blue-300` | Spinner |
| complete | `bg-green-100 text-green-700` | `bg-green-500` | `border-green-300` | Checkmark |
| failed | `bg-red-100 text-red-700` | `bg-red-500` | `border-red-300` | X mark |
| active | `bg-blue-100 text-blue-700` | `bg-blue-500` | `border-blue-300` | Play icon |

### Status Badge Component

Reuse the `StatusBadge` component already defined in SkillProgressTracker.tsx. Extract it to a shared component for reuse:

```
// components/StatusBadge.tsx
interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md';   // sm for cards, md for page headers
}
```

- Size sm: `text-xs px-2 py-0.5`
- Size md: `text-sm px-3 py-1`

### Confidence Score Display

Three visual treatments depending on context:

**1. Inline text (workload cards):**
Not displayed on workload cards in the plan view -- confidence is only meaningful after execution.

**2. Ring gauge (progress/results pages):**
Reuse the exact SVG ring from SkillProgressTracker.tsx:
- radius=36, strokeWidth=8, viewBox "0 0 88 88"
- Color thresholds:
  - >= 85%: `#22c55e` (green-500)
  - >= 65%: `#f59e0b` (amber-500)
  - < 65%: `#3b82f6` (blue-500)
  - Failed: `#ef4444` (red-500)

**3. Text with color (results summary):**
- `text-2xl font-bold` with color matching thresholds above
- Matches existing SkillRunResults.tsx pattern

### Typography

All values match existing usage in the codebase:

| Element | Class |
|---------|-------|
| Page title | `text-2xl font-bold` |
| Section heading | `text-lg font-semibold` |
| Card title | `text-base font-semibold text-gray-900` |
| Body text | `text-sm text-gray-700` |
| Secondary text | `text-sm text-gray-500` |
| Tertiary text | `text-xs text-gray-400` |
| Label (uppercase) | `text-xs font-medium text-gray-400 uppercase tracking-wider` |
| Monospace values | `font-mono text-sm` |
| Large stat value | `text-3xl font-bold text-gray-900` or `text-4xl font-bold text-gray-800` |

### Spacing

| Context | Token |
|---------|-------|
| Page sections | `space-y-8` (matches Dashboard) |
| Within a card | `space-y-3` or `space-y-4` |
| Card padding | `p-5` or `p-6` |
| Card gap in grid | `gap-6` |
| Card border | `rounded-lg shadow-sm border border-gray-200` or `rounded-xl shadow-sm border border-gray-100` |

### Shadows

- Summary cards: `shadow-sm` (subtle)
- Modals: `shadow-2xl` (matches existing ArtifactViewer modal)
- Hover on cards: `hover:shadow-md transition-shadow` (matches Dashboard cards)

---

## 7. Component Hierarchy

### New Components to Build

```
frontend/src/
  api/
    hooks/
      usePlans.ts                  -- React Query hooks for plan endpoints
  components/
    StatusBadge.tsx                 -- Extracted from SkillProgressTracker (shared)
    PlanReviewModal.tsx             -- Modal shown after plan generation
    PhaseTimeline.tsx               -- Horizontal connected-dot phase visualization
    PhaseAccordion.tsx              -- Collapsible phase section
    WorkloadCard.tsx                -- Card for a workload within a phase
    PlanProgressBar.tsx             -- Overall plan completion bar
    MigrationCard.tsx              -- Dashboard card for a single migration
  pages/
    MigrationPlan.tsx              -- /plans/:planId
    WorkloadDetail.tsx             -- /workloads/:workloadId
```

### usePlans.ts -- API Hooks

```typescript
// Planned hook signatures:

// Fetch a plan with phases and workloads
usePlan(planId: string): UseQueryResult<PlanOut>

// Fetch plan status (with polling support)
usePlanStatus(planId: string): UseQueryResult<PlanOut>

// Generate a plan for a migration
useGeneratePlan(): UseMutationResult<PlanOut, Error, { migrationId: string }>

// Delete a plan
useDeletePlan(): UseMutationResult<void, Error, string>

// Execute a workload
useExecuteWorkload(): UseMutationResult<{ skill_run_id: string }, Error, string>

// Fetch workload resources (individual workload's linked resources)
// This may require a new backend endpoint: GET /api/workloads/{id}/resources
useWorkloadResources(workloadId: string): UseQueryResult<Resource[]>
```

### Component Props

**PlanReviewModal**
```typescript
interface PlanReviewModalProps {
  plan: PlanOut;
  migrationName: string;
  isOpen: boolean;
  onClose: () => void;             // closes modal without action
  onDiscard: () => void;           // deletes plan and closes
  onOpenPlan: () => void;          // navigates to plan page
}
```

**PhaseTimeline**
```typescript
interface PhaseTimelineProps {
  phases: PhaseOut[];
  currentPhaseIndex: number;       // index of the first non-complete phase
}
```

**PhaseAccordion**
```typescript
interface PhaseAccordionProps {
  phase: PhaseOut;
  phaseIndex: number;              // 0-based
  isUnlocked: boolean;             // true if previous phase is complete
  isExpanded: boolean;
  onToggle: () => void;
  onExecuteWorkload: (workloadId: string) => void;
  onExecuteAllWorkloads: () => void;
}
```

**WorkloadCard**
```typescript
interface WorkloadCardProps {
  workload: WorkloadOut;
  isPhaseUnlocked: boolean;
  previousPhaseName?: string;      // for "Blocked" tooltip text
  onExecute: () => void;
  onViewProgress: () => void;
  onViewResults: () => void;
  onRetry: () => void;
}
```

**MigrationCard**
```typescript
interface MigrationCardProps {
  migration: Migration;
  plan: PlanOut | null;
  onGeneratePlan: () => void;
  isGenerating: boolean;
}
```

### Component Reuse Map

| New Page/Component | Reuses Existing |
|--------------------|----------------|
| WorkloadDetail (Progress tab) | SkillProgressTracker.tsx (as-is) |
| WorkloadDetail (Results tab) | ArtifactViewer.tsx (as-is), SkillRunResults summary pattern |
| WorkloadDetail (Overview tab) | ResourceTable.tsx (read-only mode) |
| PhaseTimeline | Pipeline visualization pattern from SkillProgressTracker |
| PlanReviewModal | Modal overlay pattern from ArtifactViewer.tsx |
| StatusBadge | Extracted from SkillProgressTracker.tsx |
| MigrationPlan page | Tab navigation pattern from SkillRunResults.tsx |

---

## 8. Interaction States

### Plan Generation Flow

```
[Generate Plan button]
    |
    | click
    v
[Confirm dialog]: "Generate a migration plan for {migration.name}?
                    This will analyze {N} resources and create an
                    execution plan."
    |
    | confirm
    v
[Button becomes: "Generating..." with spinner, disabled]
    |
    | POST /api/migrations/{id}/plan
    |
    +-- success --> [PlanReviewModal opens with plan data]
    |
    +-- error (400) --> [Error banner: "No resources found" or API message]
    |                    [Button returns to default state]
    |
    +-- error (500) --> [Error banner: "Failed to generate plan. Try again."]
                        [Button returns to default state]
```

### Workload Execution Flow

```
[Execute button on workload card or detail page]
    |
    | click
    v
[Confirm dialog]: "Execute this workload?
                    This will translate {N} resources using {skill_type}.
                    Estimated time: 1-5 minutes."
    |
    | confirm
    v
[Button becomes: "Starting..." with spinner]
    |
    | POST /api/workloads/{id}/execute
    |
    +-- success (202) --> [Workload card status changes to "running"]
    |                      [If on WorkloadDetail: switch to Progress tab]
    |                      [SSE stream begins via skill_run_id]
    |
    +-- error (409) --> [Toast: "Workload is already running"]
    |
    +-- error (400) --> [Toast: "Workload has no skill type assigned"]
    |
    +-- error (500) --> [Error banner on card: "Failed to start. Try again."]
                        [Execute button returns to default]
```

### Loading States

| Component | Loading State |
|-----------|--------------|
| Dashboard migration cards | Skeleton: `animate-pulse` gray rectangles matching card layout (2 cards) |
| MigrationPlan page | Full-page centered spinner (same as SkillRunResults loading) |
| Phase accordion content | Skeleton: 1-2 `animate-pulse` card-shaped rectangles |
| WorkloadDetail resource table | Skeleton: 3 rows of `animate-pulse h-10 bg-gray-100 rounded` (matches SkillRunNew) |
| Plan generation | Button spinner + no other page changes |

### Empty States

| Context | Message | Action |
|---------|---------|--------|
| Dashboard, no migrations | "No migrations yet. Connect an AWS account and discover resources to get started." | Link to /settings |
| Dashboard, migration with 0 resources | "No resources discovered yet." | "Discover Resources" button (if applicable) |
| MigrationPlan, plan deleted or not found | "Plan not found. It may have been deleted." | "Back to Dashboard" link |
| WorkloadDetail, no resources in workload | "No resources linked to this workload." | -- (should not happen in normal flow) |
| Plan with 0 phases | "No translatable resources found. The plan has no phases because the discovered resources don't match any supported skill types." | List of supported types as hint |

### Error States

All error banners follow the existing pattern from SkillRunNew.tsx:

```html
<div className="p-3 bg-red-50 text-red-700 rounded-lg text-sm" role="alert">
  {errorMessage}
</div>
```

For failed workloads, the error section is more prominent:

```html
<div className="bg-red-50 border border-red-200 rounded-lg p-4">
  <h3 className="text-red-800 font-semibold mb-2">Execution Failed</h3>
  <pre className="text-red-700 text-sm whitespace-pre-wrap">
    {errorDetails}
  </pre>
  <button className="mt-3 ...">Retry Execution</button>
</div>
```

This matches the existing error display in SkillRunResults.tsx.

### Toast Notifications

For transient feedback (plan discarded, execution started, etc.), use a simple toast pattern:

- Position: `fixed bottom-6 right-6 z-50`
- Container: `bg-gray-900 text-white px-4 py-3 rounded-lg shadow-lg text-sm`
- Auto-dismiss after 4 seconds with fade-out
- Types:
  - Success: green left-border accent `border-l-4 border-green-400`
  - Error: red left-border accent `border-l-4 border-red-400`
  - Info: blue left-border accent `border-l-4 border-blue-400`

---

## 9. Accessibility Notes

### Keyboard Navigation

- All buttons and links must be focusable and operable via Enter/Space.
- Phase accordion headers: focusable with `tabindex="0"`, toggle on Enter/Space. Use `aria-expanded` attribute.
- Tab navigation (Overview/Progress/Results): use `role="tablist"`, `role="tab"`, `role="tabpanel"`, `aria-selected`.
- Modal (PlanReviewModal): trap focus inside modal when open. Close on Escape key. Return focus to trigger button on close.
- Workload cards within phases: focusable, with Enter navigating to WorkloadDetail.

### ARIA Attributes

| Element | ARIA |
|---------|------|
| Phase accordion trigger | `role="button"`, `aria-expanded="true/false"`, `aria-controls="phase-{id}-content"` |
| Phase accordion content | `id="phase-{id}-content"`, `role="region"`, `aria-labelledby="phase-{id}-header"` |
| Status badges | `role="status"`, `aria-label="Status: {status}"` |
| Progress bar | `role="progressbar"`, `aria-valuenow={percent}`, `aria-valuemin="0"`, `aria-valuemax="100"`, `aria-label="Plan completion: {percent}%"` |
| Phase timeline dots | `aria-label="Phase {N}: {name} - {status}"` |
| Modal overlay | `role="dialog"`, `aria-modal="true"`, `aria-labelledby="modal-title"` |
| Confirm dialogs | Use native `confirm()` (inherently accessible) or build accessible dialog with focus management |
| Disabled buttons | `aria-disabled="true"` alongside `disabled` attribute; include `title` or `aria-label` explaining why |

### Color Contrast

All status color combinations meet WCAG AA contrast requirements:
- `text-gray-700` on `bg-gray-100`: 7.5:1 ratio (passes AAA)
- `text-blue-700` on `bg-blue-100`: 5.6:1 ratio (passes AA)
- `text-green-700` on `bg-green-100`: 5.2:1 ratio (passes AA)
- `text-red-700` on `bg-red-100`: 5.4:1 ratio (passes AA)

### Screen Reader Announcements

- When plan generation completes: use `aria-live="polite"` region to announce "Migration plan generated with {N} phases."
- When workload execution completes: announce "Workload {name} completed with {confidence}% confidence."
- When a phase transitions to complete: announce "Phase {N} {name} complete."

### Motion Preferences

- All animations (spinner, progress bar transitions, accordion slide) should respect `prefers-reduced-motion`:
  ```css
  @media (prefers-reduced-motion: reduce) {
    .animate-pulse, .animate-spin { animation: none; }
    .transition-all, .transition-colors, .transition-transform { transition: none; }
  }
  ```

---

## 10. New Routes and Navigation

### Route Definitions

Add to the existing React Router configuration:

```
/plans/:planId          -->  MigrationPlan.tsx
/workloads/:workloadId  -->  WorkloadDetail.tsx
```

### Navigation Sidebar/Header Updates

If the app has a sidebar or top nav, add a "Plans" item that links to the Dashboard (plans are accessed through migration cards, not a standalone list).

### Breadcrumb Trail

For deep pages, show a text breadcrumb at the top:

**MigrationPlan page:**
```
Dashboard > Acme Corp Migration > Plan
```

**WorkloadDetail page:**
```
Dashboard > Acme Corp Migration > Plan > Networking Foundation workload
```

Breadcrumb styling: `text-sm text-gray-500` with `>` separator, links in `text-blue-600 hover:text-blue-800`.

### Deep Link Support

All pages must be directly linkable:
- `/plans/{uuid}` -- loads plan data via GET /api/plans/{id}
- `/workloads/{uuid}` -- loads workload data (requires a new GET /api/workloads/{id} endpoint or derivable from plan data)

### Navigation from Existing Pages

| From | To | Trigger |
|------|-----|---------|
| Dashboard | PlanReviewModal | "Generate Plan" button on migration card |
| Dashboard | MigrationPlan | "View Plan" button on migration card |
| PlanReviewModal | MigrationPlan | "Open Plan" button |
| MigrationPlan | WorkloadDetail | Click workload card or "View Progress"/"View Results" link |
| MigrationPlan | Dashboard | "Back to Dashboard" link |
| WorkloadDetail | MigrationPlan | "Back to Plan" link |
| WorkloadDetail | SkillRunResults | Optional: "View Full Skill Run" link (for advanced users) |

---

## Appendix A: Backend Endpoint Gaps

The following endpoints may need to be added or confirmed:

1. **GET /api/workloads/{id}** -- Needed for WorkloadDetail page to load a single workload with its phase/plan context. The current API only exposes workloads nested inside plan responses. This endpoint should return the workload plus its parent phase name, plan ID, and linked resource details.

2. **GET /api/workloads/{id}/resources** -- Returns the full Resource objects linked to a workload (not just IDs). Needed for the resource table on WorkloadDetail. Alternatively, the GET /api/workloads/{id} endpoint could include resources inline.

3. **GET /api/migrations/{id}/plan** -- A convenience endpoint to check if a plan exists for a migration and return its ID/status. Currently the frontend would need to load the full migration with plan relationship. This could alternatively be included in the existing GET /api/migrations response.

## Appendix B: Polling and SSE Strategy

### Plan Page Polling

- Use React Query `refetchInterval` on `usePlanStatus(planId)`.
- Poll every 3000ms when any phase has status "running".
- Stop polling when plan status is "complete", "failed", or all phases are either "complete", "failed", or "pending" (no active work).

### Workload Execution SSE

- Reuse the existing `useSkillRunStream` hook from `useSkillRuns.ts`.
- The SSE endpoint is `GET /api/skill-runs/{skillRunId}/stream`.
- The workload's `skill_run_id` field (populated after POST /api/workloads/{id}/execute) provides the skill run ID for the stream.
- The `SkillProgressTracker` component handles SSE connection, reconnection, and cleanup.

### Data Freshness

- After any mutation (execute, delete, retry), invalidate the `['plans', planId]` query key.
- After workload execution completes (detected via SSE "done" event), invalidate both `['plans', planId]` and `['skill-runs']` query keys.
