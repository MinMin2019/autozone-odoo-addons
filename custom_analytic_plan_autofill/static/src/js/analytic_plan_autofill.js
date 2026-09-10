/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

/**
 * ฟิลเตอร์ Analytic ของรายงานบัญชี: เมื่อผู้ใช้เพิ่ม "แผน" (โซน เช่น ZONE 1)
 * ให้เติม analytic account ทุกตัวที่สังกัดแผนนั้น (รวมแผนลูก, เฉพาะ active)
 * เข้าช่อง "บัญชี" ให้อัตโนมัติ — ผลคือได้คอลัมน์รวมโซน + รายสาขาในคลิกเดียว
 *
 * เติมเฉพาะตอน "เพิ่ม" แผนเท่านั้น: ผู้ใช้ยังถอดสาขารายตัวออกได้
 * และการถอดแผนออกจะไม่ไปลบสาขาที่เลือกไว้แล้ว
 */
patch(AccountReportFilters.prototype, {
    getMultiRecordSelectorProps(resModel, optionKey) {
        const props = super.getMultiRecordSelectorProps(resModel, optionKey);
        if (optionKey !== "analytic_plans_groupby") {
            return props;
        }
        return {
            ...props,
            update: async (resIds) => {
                const previousPlans = (this.controller.options.analytic_plans_groupby || []).map(Number);
                const addedPlans = resIds.map(Number).filter((id) => !previousPlans.includes(id));
                if (addedPlans.length) {
                    const accountIds = await this.orm.search("account.analytic.account", [
                        ["plan_id", "child_of", addedPlans],
                    ]);
                    const current = (this.controller.options.analytic_accounts_groupby || []).map(Number);
                    const merged = [...current, ...accountIds.filter((id) => !current.includes(id))];
                    if (merged.length !== current.length) {
                        await this.controller.updateOption("analytic_accounts_groupby", merged);
                    }
                }
                this.filterClicked({ optionKey, optionValue: resIds, reload: true });
            },
        };
    },
});
