"""Canonical playbooks per failure mode and ambiguous combination.

Each playbook is a dict with:
    root_causes: list[str]   - candidate root cause hypotheses, most likely first
    actions:     list[str]   - recommended next actions, highest priority first

Strings may contain {placeholder} fields filled per row by build_dataset.py.
Available placeholders:
    {variant}, {rpm}, {torque}, {tool_wear}, {power_w},
    {air_t}, {proc_t}, {delta_t}, {torque_x_wear}, {osf_limit}
"""

from __future__ import annotations

from typing import TypedDict


class Playbook(TypedDict):
    root_causes: list[str]
    actions: list[str]


PLAYBOOKS: dict[str, Playbook] = {
    "TWF": {
        "root_causes": [
            "Tool has reached end-of-life wear ({tool_wear} min, inside the 200–240 min replacement window)",
            "Cutting edge degradation causing increased cutting force and chatter",
            "Missed scheduled tool change for product variant {variant}",
        ],
        "actions": [
            "Stop the spindle and replace the cutting tool before resuming the job",
            "Inspect the spindle taper and tool holder for wear-induced runout",
            "Verify the next scheduled tool change in the maintenance plan covers this product variant",
            "Check finished pieces from the last cycle for dimensional drift or surface defects",
        ],
    },
    "HDF": {
        "root_causes": [
            "Insufficient heat dissipation: ΔT process−air only {delta_t} K (below 8.6 K) at low spindle speed {rpm} rpm",
            "Coolant flow loss or blocked nozzle on the cutting zone",
            "Fouled heat exchanger or fan obstruction reducing convective cooling",
            "Ambient temperature ({air_t} K) elevated by adjacent process or HVAC failure",
        ],
        "actions": [
            "Pause the job and let the spindle cool before restart",
            "Inspect coolant flow rate, filter, and nozzle alignment",
            "Clean cooling fins and verify the cooling fan is running at rated speed",
            "Check ambient conditions at the cell — ventilation, neighboring heat sources",
            "Increase rotational speed above 1380 rpm if process plan allows, to improve forced convection",
        ],
    },
    "PWF_LOW": {
        "root_causes": [
            "Drivetrain power below 3500 W ({power_w} W) — possible belt slip, coupling failure, or free-spin",
            "Torque sensor drift reading artificially low ({torque} Nm at {rpm} rpm)",
            "Workpiece not engaging the tool (clamping or part-loading fault)",
            "Spindle motor under-excitation or VFD parameter drift",
        ],
        "actions": [
            "Verify the workpiece is correctly clamped and engaged with the tool",
            "Inspect drive belts, couplings, and spindle for slippage or backlash",
            "Re-zero / calibrate the torque sensor and compare with current draw on the drive",
            "Review VFD parameters for unexpected ramp or current limits",
        ],
    },
    "PWF_HIGH": {
        "root_causes": [
            "Drivetrain power above 9000 W ({power_w} W) — overload from high torque ({torque} Nm) at {rpm} rpm",
            "Feed rate or depth of cut too aggressive for current tool and material",
            "Workpiece jam or chip packing in the cutting zone increasing resistance",
            "Spindle bearing degradation adding parasitic load",
        ],
        "actions": [
            "Stop the spindle immediately and clear any chips or jam at the cutting zone",
            "Reduce feed rate / depth of cut and re-run a test part",
            "Inspect spindle bearings for noise, heat, and end-play",
            "Verify drive overcurrent protection trip points are configured correctly",
        ],
    },
    "OSF": {
        "root_causes": [
            "Overstrain: torque×wear {torque_x_wear} minNm exceeds the {osf_limit} minNm limit for variant {variant}",
            "Tool wear ({tool_wear} min) combined with high cutting torque ({torque} Nm) — compound mechanical stress",
            "Workpiece harder than spec or incorrect material variant loaded",
        ],
        "actions": [
            "Halt the job and replace the tool before mechanical damage propagates",
            "Inspect the spindle and tool holder for cracking, deformation, or runout",
            "Verify the loaded material matches the planned variant {variant}",
            "Lower feed rate and run a test part to bring torque×wear back inside the {osf_limit} minNm envelope",
        ],
    },
    "RNF": {
        "root_causes": [
            "Random / unexplained failure — no documented sensor rule was breached",
            "Possible transient: control glitch, intermittent sensor fault, or untracked external disturbance",
            "Latent defect not reflected in the monitored signals (lubrication, electrical, environmental)",
        ],
        "actions": [
            "Capture full sensor traces and event logs around the failure timestamp for review",
            "Run a diagnostic dry-cycle and watch for repeat anomalies",
            "Inspect lubrication, electrical connections, and any sensors flagged as marginal",
            "Escalate to maintenance engineering if the failure repeats within the next 24 h",
        ],
    },
    "HDF_PWF": {
        "root_causes": [
            "Compound thermal + electrical event: ΔT only {delta_t} K and power off-band at {power_w} W",
            "Cooling loss is loading the drivetrain — motor working harder against thermal expansion / seized parts",
            "Shared root cause likely: coolant or auxiliary system failure cascading into drive load",
        ],
        "actions": [
            "Stop the job and isolate the cell — both thermal and power envelopes are breached",
            "Inspect coolant supply and the spindle drive simultaneously",
            "Check for mechanical binding induced by thermal expansion in the spindle assembly",
            "Review controller logs for correlated coolant and drive alarms in the prior shift",
        ],
    },
    "OSF_TWF": {
        "root_causes": [
            "Worn tool ({tool_wear} min) combined with overstrain (torque×wear {torque_x_wear} minNm > {osf_limit})",
            "Cascade: end-of-life tool causing torque to climb until the OSF envelope was exceeded",
            "Missed tool change driving compound mechanical failure on variant {variant}",
        ],
        "actions": [
            "Stop and replace the cutting tool immediately",
            "Inspect spindle, holder, and workpiece for damage from sustained over-torque",
            "Audit the tool-life policy for variant {variant} — the wear limit was reached and exceeded",
            "Run a post-change qualification part before returning the cell to production",
        ],
    },
    "NORMAL": {
        "root_causes": [
            "No failure detected — all monitored signals within safe operating bands",
        ],
        "actions": [
            "Continue routine monitoring",
            "No intervention required at this time",
        ],
    },
}


def select_playbook_key(
    primary_mode: str,
    triggered_modes: list[str],
    pwf_side: str | None,
) -> str:
    """Pick a playbook key from primary mode + triggered set + PWF side.

    For ambiguous multi-mode rows we prefer the curated combo playbooks
    (HDF_PWF, OSF_TWF) when their pair is exactly the triggered set;
    otherwise fall back to the primary mode's single-mode playbook.
    The caller is responsible for merging in causes from secondary modes
    when no combo playbook applies.
    """
    triggered = set(triggered_modes)
    if triggered == {"HDF", "PWF"}:
        return "HDF_PWF"
    if triggered == {"OSF", "TWF"}:
        return "OSF_TWF"
    if primary_mode == "PWF":
        return "PWF_LOW" if pwf_side == "low" else "PWF_HIGH"
    if primary_mode in PLAYBOOKS:
        return primary_mode
    return "NORMAL"
