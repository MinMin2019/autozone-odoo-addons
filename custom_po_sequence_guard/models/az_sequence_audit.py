# -*- coding: utf-8 -*-
"""บันทึกการเปลี่ยนค่า ir_sequence.number_next ด้วย trigger ของ PostgreSQL

ที่มา: 24 ก.ย. 2026 ตัวนับเลข PO ถอยจาก 180 เป็น 176 โดยไม่มีร่องรอยใน log ของ Odoo
(ได้ PO202609176-178 ซ้ำ) -> ใช้ trigger จับทุกทาง ทั้ง ORM, odoo shell และ SQL ตรง
เก็บ: เฉพาะตัวนับ purchase.order ทุกครั้ง + ตัวนับอื่นเฉพาะตอนค่าถอยหลัง
"""
from odoo import fields, models


class AzSequenceAudit(models.Model):
    _name = "az.sequence.audit"
    _description = "Sequence Audit"
    _order = "id desc"
    _log_access = False

    at = fields.Datetime("เวลา", readonly=True)
    sequence_id = fields.Integer("Sequence ID", readonly=True)
    sequence_code = fields.Char("Code", readonly=True)
    old_next = fields.Integer("ค่าเดิม", readonly=True)
    new_next = fields.Integer("ค่าใหม่", readonly=True)
    backwards = fields.Boolean("ถอยหลัง", readonly=True)
    db_user = fields.Char("DB User", readonly=True)
    app_name = fields.Char("Application", readonly=True, help="odoo-<pid>: pid ของ service = ผ่านหน้าเว็บ, pid อื่น = odoo shell/สคริปต์, psql = SQL ตรง")
    client_addr = fields.Char("Client", readonly=True)
    backend_pid = fields.Integer("Backend PID", readonly=True)
    query = fields.Text("Query", readonly=True)

    def init(self):
        cr = self.env.cr
        cr.execute("""
            CREATE OR REPLACE FUNCTION az_sequence_audit_fn() RETURNS trigger AS $$
            BEGIN
                IF NEW.number_next IS DISTINCT FROM OLD.number_next
                   AND (NEW.code = 'purchase.order' OR NEW.number_next < OLD.number_next) THEN
                    INSERT INTO az_sequence_audit
                        (at, sequence_id, sequence_code, old_next, new_next, backwards,
                         db_user, app_name, client_addr, backend_pid, query)
                    VALUES
                        (now() AT TIME ZONE 'UTC', NEW.id, NEW.code, OLD.number_next, NEW.number_next,
                         NEW.number_next < OLD.number_next, current_user,
                         current_setting('application_name', true), inet_client_addr()::text,
                         pg_backend_pid(), left(current_query(), 2000));
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        cr.execute("DROP TRIGGER IF EXISTS az_sequence_audit_trg ON ir_sequence")
        cr.execute("""
            CREATE TRIGGER az_sequence_audit_trg
            AFTER UPDATE OF number_next ON ir_sequence
            FOR EACH ROW EXECUTE FUNCTION az_sequence_audit_fn()
        """)
