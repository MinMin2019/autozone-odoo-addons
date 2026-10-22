from odoo import _, api, fields, models


class HrDepartment(models.Model):
    _inherit = "hr.department"

    # Stock hr.department sorts by name, so the org chart comes out in Thai
    # alphabetical order — which scatters the สายงาน groupings that FM-HR-36
    # is read by. The order the departments were entered in already follows the
    # paper chart (executive offices, then กำกับ, then พัฒนาธุรกิจ, then
    # ปฏิบัติการ; branches grouped by zone), so sequence is seeded from that and
    # stays draggable from the list view afterwards.
    _order = "sequence, id"

    sequence = fields.Integer(
        string="Sequence",
        default=100,
        index=True,
        help="Order the department appears in, on the org chart and everywhere "
             "else. Drag the rows in the Departments list to change it.",
    )

    # Stock display is complete_name — "บริษัท ออโต้โซน จำกัด / สายงานปฏิบัติการ /
    # ฝ่ายธุรกิจ SUBCONTRACT / แผนกศูนย์ซ่อมสีและตัวถัง / ภาค 2 / สาขา BPA" — which
    # a form field cuts off long before the part that matters. Show the
    # department and its parent instead: short enough to read, and the parent
    # tells apart the two แผนกศูนย์ซ่อมสีและตัวถัง (one under each ฝ่ายธุรกิจ).
    # Typing still searches complete_name, so "BPA" or "SUBCONTRACT" both find it.
    @api.depends_context("hierarchical_naming")
    @api.depends("name", "parent_id.name")
    def _compute_display_name(self):
        if not self.env.context.get("hierarchical_naming", True):
            return super()._compute_display_name()
        for department in self:
            parent = department.parent_id
            department.display_name = (f"{department.name} ({parent.name})"
                                        if parent and parent.parent_id else department.name)

    analytic_account_id = fields.Many2one(
        comodel_name="account.analytic.account",
        string="Analytic Account",
        ondelete="restrict",
        check_company=True,
        tracking=True,
        help="Set this on BRANCH departments only, and leave it empty on ภาค and "
             "everything above.\n\n"
             "Reporting lines follow whatever reassignment the org chart makes, "
             "while a branch keeps posting to the analytic account for its "
             "geography — ICR and VWT report to the อีสาน zone manager but still "
             "post to ZONE 3. Holding the link here, at the branch, is what lets "
             "the next reassignment move parent_id without touching the books.",
    )

    # The branch it belongs to is what makes a clock-in, an expense or a
    # timesheet land in the right ledger, so surface it on the parent too —
    # read-only, since the value belongs to the branch that owns it.
    parent_analytic_account_id = fields.Many2one(
        comodel_name="account.analytic.account",
        string="Analytic Account (parent)",
        related="parent_id.analytic_account_id",
        readonly=True,
    )

    # Odoo's list has no tree mode, so folding is carried in the data instead of
    # the renderer: each department remembers whether it is folded, a row is
    # visible only while every ancestor above it is open, and the caret is an
    # ordinary list button that writes the flag. No custom JS, nothing to break
    # on an upgrade.
    is_folded = fields.Boolean(
        string="Folded", default=True, copy=False,
        help="Whether this department's children are hidden in the list.",
    )
    is_visible_in_tree = fields.Boolean(
        string="Visible In Tree",
        compute="_compute_is_visible_in_tree",
        store=True,
        recursive=True,
        index=True,
        export_string_translation=False,
    )
    has_children = fields.Boolean(
        compute="_compute_has_children", export_string_translation=False,
    )

    @api.depends("parent_id.is_visible_in_tree", "parent_id.is_folded")
    def _compute_is_visible_in_tree(self):
        for department in self:
            parent = department.parent_id
            department.is_visible_in_tree = (
                True if not parent else parent.is_visible_in_tree and not parent.is_folded
            )

    @api.depends("child_ids")
    def _compute_has_children(self):
        for department in self:
            department.has_children = bool(department.child_ids)

    # These return True rather than falling off the end: the web client reloads
    # on anything that is not an action dict either way, and None cannot cross
    # XML-RPC, which is how the behaviour gets tested.
    def action_unfold(self):
        self.is_folded = False
        return True

    def action_fold(self):
        """Fold this one and everything under it.

        Folding only this department would leave its descendants' own flags
        open, so re-opening it would spill the whole branch back at once
        instead of one level.
        """
        self.search([("id", "child_of", self.ids)]).is_folded = True
        return True

    def action_unfold_all(self):
        self.search([]).is_folded = False
        return True

    def action_fold_all(self):
        self.search([]).is_folded = True
        return True

    # Pinning each ancestor to its own field is what lets a pivot or a graph
    # slice by สายงาน / ฝ่าย / แผนก. It also drives multi-level group_by, though
    # the list is deliberately left ungrouped — see the note in the view file.
    line_id = fields.Many2one(
        "hr.department", string="สายงาน", compute="_compute_ancestors",
        store=True, recursive=True, index=True,
    )
    division_id = fields.Many2one(
        "hr.department", string="ฝ่าย", compute="_compute_ancestors",
        store=True, recursive=True, index=True,
    )
    section_id = fields.Many2one(
        "hr.department", string="แผนก", compute="_compute_ancestors",
        store=True, recursive=True, index=True,
    )

    @api.depends("parent_path")
    def _compute_ancestors(self):
        # parent_path is '2/298/5/' — the whole chain from the root, self last.
        # Index 0 is the executive office at the top, so the line is index 1.
        for department in self:
            chain = [int(i) for i in (department.parent_path or "").split("/") if i]
            department.line_id = chain[1] if len(chain) > 1 else False
            department.division_id = chain[2] if len(chain) > 2 else False
            department.section_id = chain[3] if len(chain) > 3 else False

    # A list view cannot nest rows, so the tree is carried two ways instead: a
    # sort key that puts every department straight after its parent, and a name
    # padded by depth. Sorting the list by anything else makes the padding lie,
    # which is why the view pins default_order to this key.
    hierarchy_sequence = fields.Char(
        string="Tree Order",
        compute="_compute_hierarchy_sequence",
        store=True,
        recursive=True,
        index=True,
        export_string_translation=False,
    )
    hierarchy_depth = fields.Integer(
        string="Depth", compute="_compute_name_indented", export_string_translation=False,
    )
    name_indented = fields.Char(
        string="Department",
        compute="_compute_name_indented",
        export_string_translation=False,
    )

    @api.depends("sequence", "parent_id.hierarchy_sequence")
    def _compute_hierarchy_sequence(self):
        for department in self:
            own = str(department.sequence or 0).zfill(6)
            parent_key = department.parent_id.hierarchy_sequence
            department.hierarchy_sequence = f"{parent_key}/{own}" if parent_key else own

    @api.depends("name", "parent_path")
    def _compute_name_indented(self):
        for department in self:
            # parent_path is '2/298/5/' — one segment per ancestor including self.
            depth = max((department.parent_path or "").count("/") - 1, 0)
            department.hierarchy_depth = depth
            pad = " " * (depth * 4)
            department.name_indented = f"{pad}{department.name or ''}"

    # Which plan the branch posts to. Read-only and derived — the branch owns the
    # account, the account owns the plan; seeing the plan here is what makes a
    # mismatch obvious (ICR and VWT report to the อีสาน zone but post to ZONE 3).
    analytic_plan_id = fields.Many2one(
        comodel_name="account.analytic.plan",
        string="Analytic Plan",
        related="analytic_account_id.plan_id",
        readonly=True,
    )

    expected_employees = fields.Integer(
        string="Expected Employees",
        compute="_compute_expected_employees",
        help="Headcount the job positions on this department add up to — those "
             "already filled plus those still being recruited.",
    )

    @api.depends("jobs_ids.expected_employees")
    def _compute_expected_employees(self):
        for department in self:
            department.expected_employees = sum(department.jobs_ids.mapped("expected_employees"))

    # What the org chart's vacancy badge reads. It used to key off an empty
    # manager_id, which was true of every department in the database and so
    # said "everything is vacant" when the truth was "nobody filled in
    # department managers". An open position is a job with a recruitment
    # target, which is a deliberate act — and is also what Recruitment will
    # read once it is installed.
    # Stored so it can be filtered on — an unstored compute is silently dropped
    # from a search domain, which makes "show me the departments recruiting"
    # return every department instead of the four.
    open_positions = fields.Integer(
        string="Open Positions",
        compute="_compute_open_positions",
        store=True,
        help="Headcount still being recruited for, summed over the job "
             "positions on this department. Drives the ตำแหน่งว่าง badge.",
    )

    @api.depends("jobs_ids.no_of_recruitment")
    def _compute_open_positions(self):
        for department in self:
            department.open_positions = sum(department.jobs_ids.mapped("no_of_recruitment"))

    # Roll-ups of the establishment plan, so a ฝ่าย or a สาขา can be read
    # without opening its job positions one by one.
    approved_headcount = fields.Integer(
        string="อัตราที่อนุมัติ",
        compute="_compute_headcount_plan",
        store=True,
        help="Approved establishment summed over this department's own job "
             "positions (not its sub-departments).",
    )
    headcount_gap = fields.Integer(
        string="ขาด/เกิน",
        compute="_compute_headcount_plan",
        store=True,
        help="Filled minus approved, summed over this department's job "
             "positions. Negative means short-handed.",
    )

    @api.depends("jobs_ids.approved_headcount", "jobs_ids.headcount_gap")
    def _compute_headcount_plan(self):
        for department in self:
            department.approved_headcount = sum(department.jobs_ids.mapped("approved_headcount"))
            department.headcount_gap = sum(department.jobs_ids.mapped("headcount_gap"))

    total_employee_all = fields.Integer(
        string="Employees (incl. sub-departments)",
        compute="_compute_total_employee_all",
        export_string_translation=False,
        help="Everyone under this department, all the way down. Stock "
             "total_employee counts only employees whose department is this one "
             "exactly, and at Autozone people sit in the งาน leaves — so every "
             "ฝ่าย and สายงาน reads 0, which is true and useless.",
    )

    @api.depends("parent_path", "member_ids")
    def _compute_total_employee_all(self):
        # Two queries for the whole tree, not one per department: head counts per
        # department, then parent_path prefix matching. _parent_store keeps
        # parent_path as '2/298/5/', so a descendant's path starts with its
        # ancestor's, and a department's own path starts with itself — which is
        # what folds the direct members in.
        counts = {
            department.id: count
            for department, count in self.env["hr.employee"].sudo()._read_group(
                [("company_id", "in", self.env.companies.ids)],
                ["department_id"],
                ["__count"],
            )
            if department
        }
        paths = {
            d["id"]: d["parent_path"] or ""
            for d in self.env["hr.department"].sudo().search_read(
                [], ["parent_path"], load=False
            )
        }
        for department in self:
            prefix = paths.get(department.id) or ""
            if not prefix:
                # No path yet (a record still being created) — fall back to the
                # direct count rather than matching every department.
                department.total_employee_all = counts.get(department.id, 0)
                continue
            department.total_employee_all = sum(
                count
                for dep_id, count in counts.items()
                if paths.get(dep_id, "").startswith(prefix)
            )

    def action_employee_from_department_all(self):
        """Same as the stock action, widened to the whole sub-tree."""
        action = self.action_employee_from_department()
        action["name"] = _("Employees")
        action["domain"] = [("department_id", "child_of", self.id)]
        return action

    @api.model
    def _seed_sequence(self):
        """Write sequence = id * 10 wherever it is still the default.

        Only touches records nobody has ordered by hand, so re-running it after
        HR has dragged rows around leaves their arrangement alone.
        """
        untouched = self.filtered(lambda d: d.sequence == 100)
        for department in untouched:
            department.sequence = department.id * 10
        return len(untouched)
