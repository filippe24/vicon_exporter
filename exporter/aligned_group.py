"""Phase 2 exports that only read the take (actors, props, scene extras), joined in one Shogun run.

Each step gives a Part: its HSL, and a finish() that runs after Shogun succeeds (move staged files,
write summaries, record the step). If Shogun fails, no finish() runs and the previous exports stay.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from exporter.aligned_export_pipeline import (
    create_aligned_export_dirs,
    generate_aligned_actor_export_hsl,
    load_aligned_export_plan,
    write_aligned_export_summary,
)
from exporter.export_status import record_step

_VARIABLE = re.compile(r"\$([A-Za-z_]\w*)")


@dataclass
class Part:
    name: str
    steps: list[str]
    hsl: str
    finish: Callable[[], None]
    warning: str | None = None
    # The actors' BVH fallbacks: static-hand BVH, then no BVH. Other parts stay the same.
    static_hand_hsl: str | None = None
    without_bvh_hsl: str | None = None


def joined_hsl(parts: list[Part], variant: str = "hsl") -> str:
    """One script with every part in order. Each part's variables get the prefix `p<n>_`, so two
    parts never declare the same variable."""
    return "\n".join(
        f"// ---- {part.name} ----\n" + _VARIABLE.sub(rf"$p{number}_\1", getattr(part, variant) or part.hsl)
        for number, part in enumerate(parts, 1)
    )


def aligned_actors_part(take_dir: Path, *, overwrite: bool = False) -> Part | None:
    plan = load_aligned_export_plan(take_dir)
    if plan is None:
        return None
    if not overwrite and plan.actors_dir.exists() and any(plan.actors_dir.iterdir()):
        print("   keeping existing aligned actor exports.")
        return None
    create_aligned_export_dirs(plan)
    print(f"   aligned actors: {plan.start_frame} -> {plan.end_frame} (aLigner YAML {plan.export_yaml_path.name})")

    def finish():
        write_aligned_export_summary(plan)
        record_step(take_dir, "actors")

    return Part(
        "actors",
        ["actors"],
        generate_aligned_actor_export_hsl(plan),
        finish,
        static_hand_hsl=generate_aligned_actor_export_hsl(plan, static_hand_bvh=True),
        without_bvh_hsl=generate_aligned_actor_export_hsl(plan, include_bvh=False),
    )
