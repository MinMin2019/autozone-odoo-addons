from . import models
from . import wizard

# The six stages hr_recruitment ships, renamed in place to the steps of HR's
# flow, plus the one it lacks. Renaming keeps their xml ids, so nothing that
# points at them (mail templates, other modules) breaks.
STAGES = [
    ("hr_recruitment.stage_job0", "ใหม่", 10, "new"),
    ("hr_recruitment.stage_job1", "คัดกรอง", 20, "screen"),
    ("hr_recruitment.stage_job2", "สัมภาษณ์", 30, "interview"),
    ("hr_recruitment.stage_job3", "ประเมินผล", 40, "evaluate"),
    ("hr_recruitment.stage_job4", "รออนุมัติจ้าง", 50, "hire_approval"),
    (None, "นัดเริ่มงาน", 60, "onboarding"),
    ("hr_recruitment.stage_job5", "เริ่มงานแล้ว", 70, "hired"),
]


def post_init_hook(env):
    Stage = env["hr.recruitment.stage"].with_context(lang="en_US")
    for xmlid, name, sequence, step in STAGES:
        stage = env.ref(xmlid, raise_if_not_found=False) if xmlid else Stage.search([("az_step", "=", step)], limit=1)
        vals = {"name": name, "sequence": sequence, "az_step": step}
        if stage:
            stage.write(vals)
        else:
            Stage.create(dict(vals, fold=False))
    # th_TH users read the translated value, so set it there too — only when
    # Thai is installed, since writing an inactive language is refused.
    if not env["res.lang"].search_count([("code", "=", "th_TH"), ("active", "=", True)]):
        return
    for xmlid, name, sequence, step in STAGES:
        stage = Stage.search([("az_step", "=", step)], limit=1)
        stage.with_context(lang="th_TH").name = name
