/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { ShAccountHierarchyWidget } from "@sh_account_parent/js/account_hierarchy_widget";

patch(ShAccountHierarchyWidget.prototype, {
    // กดกางบัญชี View ที่ยังไม่มีลูก → ของเดิมเงียบสนิท ผู้ใช้คิดว่าค้าง
    async toggleLine(line) {
        await super.toggleLine(line);
        if (!line.isFolded && !line.lines.length) {
            this.env.services.notification.add(
                _t(
                    "%s ยังไม่มีบัญชีลูก — ไปตั้ง Parent Account ของบัญชีลูกให้ชี้มาที่บัญชีนี้ก่อน",
                    `${line.code} ${line.name}`
                ),
                { type: "warning" }
            );
        }
    },
    // template มีปุ่ม Print ที่เรียก onClickPrint() แต่ class เดิมไม่มีเมธอดนี้
    onClickPrint() {
        window.print();
    },
});
