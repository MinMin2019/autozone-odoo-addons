# -*- coding: utf-8 -*-
from odoo import api, fields, models


class JobUnit(models.Model):
    """หน่วย — the layer between a department and the individual งาน.

    It used to be a department of its own, which meant every branch carried its
    own copy: "หน่วยซ่อมสีและตัวถัง สาขา (TMC)", "... (IAT)", twenty times over.
    Since a หน่วย is a kind of work rather than a place, it belongs on the job
    position, where 32 records cover what 70 departments used to.

    A model rather than a Selection so HR can add one without a developer.
    """

    _name = "hr.job.unit"
    _description = "Job Unit"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    job_ids = fields.One2many("hr.job", "unit_id", string="Job Positions")
    job_count = fields.Integer(compute="_compute_job_count")

    _sql_constraints = [
        ("name_uniq", "unique(name)", "หน่วยนี้มีอยู่แล้ว"),
    ]

    @api.depends("job_ids")
    def _compute_job_count(self):
        counts = {
            unit.id: count
            for unit, count in self.env["hr.job"]._read_group(
                [("unit_id", "in", self.ids)], ["unit_id"], ["__count"],
            )
            if unit
        }
        for unit in self:
            unit.job_count = counts.get(unit.id, 0)


class Job(models.Model):
    _inherit = "hr.job"

    # หน่วย and กลุ่มงาน are what the department tree used to carry below สาขา.
    # Keeping them here is what lets the tree stop at 57 departments instead of
    # 303 — and it is recoverable: (department, ตำแหน่ง) determined หน่วย for
    # 263 of 265 pairs in the source data.
    unit_id = fields.Many2one(
        "hr.job.unit",
        string="หน่วย",
        index=True,
        help="Which unit inside the branch or section this position sits in. "
             "Was a department level of its own until 2026-09.",
    )

    # The paint-shop split the source data already carried, in parentheses at
    # the end of every งาน name: (กลุ่มงานสี), (กลุ่มงานตัวถัง), (สำนักงาน).
    # A Selection, not a model — these four are the trade itself, not a list
    # that grows.
    work_group = fields.Selection(
        [("paint", "กลุ่มงานสี"),
         ("body", "กลุ่มงานตัวถัง"),
         ("office", "สำนักงาน"),
         ("support", "สนับสนุนองค์กร")],
        string="กลุ่มงาน",
        index=True,
        help="The trade this position belongs to. Lets a question like "
             "'how many paint-side technicians company-wide' be answered "
             "without parsing names.",
    )

    # The plan groups by ฝ่าย, which is an ancestor of the job's department
    # rather than the department itself. Stored so it can group and filter.
    division_id = fields.Many2one(
        "hr.department", string="ฝ่าย",
        related="department_id.division_id", store=True, index=True,
    )
    section_id = fields.Many2one(
        "hr.department", string="แผนก",
        related="department_id.section_id", store=True, index=True,
    )

    # --- แผนอนุมัติอัตรากำลัง (establishment plan) -------------------------
    # The seats HR has approval for, as opposed to no_of_employee (seats
    # filled) and no_of_recruitment (seats being recruited right now). Until
    # 2026-09 this lived only in "01-แผนอนุมัติอัตรากำลังคน ปี 2569.xlsx" and
    # nothing in Odoo could answer "is this branch over establishment".
    approved_headcount = fields.Integer(
        string="อัตราที่อนุมัติ",
        help="Approved establishment for this position — the seats HR has "
             "sign-off for, filled or not.",
    )
    # Positions newly created this year, as opposed to a shortfall against an
    # establishment that was already approved. The plan tracks these in a
    # separate column and they mean different things to a budget holder.
    new_positions = fields.Integer(
        string="อัตราตั้งใหม่",
        help="Seats requested as new establishment this year, from the plan's "
             "'จำนวนที่ต้องรับ / เพิ่ม' column.",
    )
    # Stored so it can be filtered and grouped — an unstored compute is
    # silently dropped from a search domain.
    headcount_gap = fields.Integer(
        string="ขาด/เกิน",
        compute="_compute_headcount_gap",
        store=True,
        help="Filled minus approved. Negative means short of establishment, "
             "positive means over it. Recomputes as people join and leave, so "
             "it is the live figure — no_of_recruitment is a snapshot.",
    )

    @api.depends("approved_headcount", "no_of_employee")
    def _compute_headcount_gap(self):
        for job in self:
            # A position the plan does not cover has no establishment to be
            # over or under. Reading 0 as "approved 0 seats" would report every
            # unplanned position — the whole management layer among them — as
            # over establishment. Use the "ยังไม่มีในแผน" filter to find these.
            job.headcount_gap = (job.no_of_employee - job.approved_headcount
                                 if job.approved_headcount else 0)

    # Autozone's own grading scheme. Stock hr.job has no field for it, and the
    # value was living only in a spreadsheet column.
    job_level = fields.Selection(
        [("TM2", "TM2"), ("TM1", "TM1"),
         ("M1", "M1"),
         ("P6", "P6"), ("P5", "P5"), ("P4", "P4"),
         ("P3", "P3"), ("P2", "P2"), ("P1", "P1"),
         ("S4", "S4"), ("S3", "S3"), ("S2", "S2"), ("S1", "S1"),
         ("G5", "G5"), ("G4", "G4"), ("G3", "G3"), ("G2", "G2"),
         ("SC", "SC")],
        string="Job Level",
        index=True,
        help="Autozone's grading band for this position.",
    )

    # One position per (role × department) is what lets each branch carry its
    # own approved headcount, so 309 positions share only 111 names — eleven
    # "คอนโทรลเลอร์", twenty-one "ช่างเตรียมพื้นผิว". A dropdown that shows the
    # name alone is a list of identical rows. job_title is computed from
    # job_id.name, not display_name, so the title on the card stays clean.
    @api.depends("name", "department_id.name")
    def _compute_display_name(self):
        for job in self:
            job.display_name = (f"{job.name} · {job.department_id.name}"
                                if job.department_id else job.name)
