/** @odoo-module **/
/*
 * หน้ารายงาน "คาดรับเงินลูกหนี้รายวัน" บนจอ แบบเดียวกับ P&L
 * - เลือกเดือน (◀ ▶ / ช่องเดือน) → ตารางลูกค้า × วันครบกำหนด (เฉพาะที่มียอด)
 * - คลิกตัวเลข → รายการใบแจ้งหนี้เบื้องหลัง, ปุ่ม PDF / Excel
 */
import { Component, onWillStart, useRef, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { ControlPanel } from "@web/search/control_panel/control_panel";
import { useSetupAction } from "@web/search/action_hook";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

function shiftMonth(month, delta) {
    const [y, m] = month.split("-").map(Number);
    const d = new Date(y, m - 1 + delta, 1);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export class ArDueForecastReport extends Component {
    static template = "custom_ar_due_forecast.ArDueForecastReport";
    static components = { ControlPanel };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.actionService = useService("action");
        this.rootRef = useRef("root");
        this.env.config.viewSwitcherEntries = [];
        this.state = useState({
            month: this.props.state?.month || this.props.action.context?.month || null,
            data: null,
            loading: false,
        });
        // จำเดือนไว้ เวลากดเข้าไปดูใบแจ้งหนี้แล้วกด breadcrumb กลับมา
        useSetupAction({
            rootRef: this.rootRef,
            getLocalState: () => ({ month: this.state.month }),
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            const data = await this.orm.call(
                "ar.due.forecast.wizard", "get_screen_data", [this.state.month || false]
            );
            this.state.data = data;
            this.state.month = data.month;
        } finally {
            this.state.loading = false;
        }
    }

    // ---------------- เดือน ----------------
    async prevMonth() {
        this.state.month = shiftMonth(this.state.month, -1);
        await this.load();
    }
    async nextMonth() {
        this.state.month = shiftMonth(this.state.month, 1);
        await this.load();
    }
    async onMonthChange(ev) {
        if (!ev.target.value) {
            return;
        }
        this.state.month = ev.target.value;
        await this.load();
    }

    // ---------------- ปุ่ม ----------------
    async printPdf() {
        const action = await this.orm.call(
            "ar.due.forecast.wizard", "action_print_pdf", [[this.state.data.wizard_id]]
        );
        await this.actionService.doAction(action);
    }
    async exportXlsx() {
        const action = await this.orm.call(
            "ar.due.forecast.wizard", "action_export_xlsx", [[this.state.data.wizard_id]]
        );
        await this.actionService.doAction(action);
    }

    // ---------------- drill-down ----------------
    async openMoves(kind, partnerId = false, day = false) {
        const action = await this.orm.call(
            "ar.due.forecast.wizard", "action_open_moves",
            [this.state.month, kind, partnerId, day]
        );
        await this.actionService.doAction(action);
    }
}

registry.category("actions").add("custom_ar_due_forecast.report", ArDueForecastReport);
