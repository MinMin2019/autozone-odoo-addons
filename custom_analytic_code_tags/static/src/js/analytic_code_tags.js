/** @odoo-module */

import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";
import { MultiRecordSelector } from "@web/core/record_selectors/multi_record_selector";

/**
 * ชิป analytic account ในแผงฟิลเตอร์รายงานบัญชี แสดงเฉพาะตัวย่อในวงเล็บเหลี่ยม
 * ("[TMC] โตโยต้า บ้านบึง" -> "TMC") — ใช้เฉพาะแผงฟิลเตอร์ของ account_reports
 * ไม่กระทบ MultiRecordSelector ที่อื่นในระบบ
 */
export class AnalyticCodeRecordSelector extends MultiRecordSelector {
    getTags(props, displayNames) {
        const tags = super.getTags(props, displayNames);
        if (props.resModel === "account.analytic.account") {
            for (const tag of tags) {
                const match = typeof tag.text === "string" ? tag.text.match(/^\[([^\]]+)\]/) : null;
                if (match) {
                    tag.text = match[1];
                }
            }
        }
        return tags;
    }
}

AccountReportFilters.components = {
    ...AccountReportFilters.components,
    MultiRecordSelector: AnalyticCodeRecordSelector,
};
