from odoo import models, fields, api, tools, _
from datetime import datetime, timedelta
import pytz
import logging

_logger = logging.getLogger(__name__)

class VietnamAttendanceReport(models.Model):
    _name = 'vietnam.attendance.report'
    _description = 'Báo cáo chấm công'
    _auto = False
    _order = 'date desc, employee_id'

    name = fields.Char(string='Tên')
    employee_id = fields.Many2one('hr.employee', string='Nhân viên', readonly=True)
    department_id = fields.Many2one('hr.department', string='Phòng ban', readonly=True)
    job_id = fields.Many2one('hr.job', string='Chức vụ', readonly=True)
    user_id = fields.Many2one('res.users', string='Người dùng', readonly=True)
    
    date = fields.Date(string='Ngày', readonly=True)
    shift_id = fields.Many2one('vietnam.attendance.shift', string='Ca làm việc', readonly=True)
    
    check_in = fields.Datetime(string='Giờ vào', readonly=True)
    check_out = fields.Datetime(string='Giờ ra', readonly=True)
    
    worked_hours = fields.Float(string='Số giờ làm việc', readonly=True)
    
    is_late = fields.Boolean(string='Đi muộn', readonly=True)
    is_early_leave = fields.Boolean(string='Về sớm', readonly=True)
    late_minutes = fields.Float(string='Số phút đi muộn', readonly=True)
    early_leave_minutes = fields.Float(string='Số phút về sớm', readonly=True)
    
    attendance_type = fields.Selection([
        ('normal', 'Bình thường'),
        ('overtime', 'Tăng ca'),
        ('business_trip', 'Công tác'),
        ('remote', 'Làm từ xa'),
    ], string='Loại chấm công', readonly=True)
    
    state = fields.Selection([
        ('draft', 'Nháp'),
        ('confirmed', 'Đã xác nhận'),
        ('approved', 'Đã duyệt'),
        ('rejected', 'Từ chối'),
    ], string='Trạng thái', readonly=True)
    
    check_in_method = fields.Selection([
        ('manual', 'Thủ công'),
        ('qrcode', 'QR Code'),
        ('face', 'Khuôn mặt'),
        ('fingerprint', 'Vân tay'),
        ('card', 'Thẻ từ'),
        ('gps', 'GPS'),
        ('wifi', 'WiFi'),
    ], string='Phương thức chấm công vào', readonly=True)
    
    check_out_method = fields.Selection([
        ('manual', 'Thủ công'),
        ('qrcode', 'QR Code'),
        ('face', 'Khuôn mặt'),
        ('fingerprint', 'Vân tay'),
        ('card', 'Thẻ từ'),
        ('gps', 'GPS'),
        ('wifi', 'WiFi'),
    ], string='Phương thức chấm công ra', readonly=True)
    
    company_id = fields.Many2one('res.company', string='Công ty', readonly=True)
    
    is_weekend = fields.Boolean(string='Cuối tuần', readonly=True)
    is_holiday = fields.Boolean(string='Ngày lễ', readonly=True)
    
    def _select(self):
        return """
            SELECT
                a.id,
                a.name,
                a.employee_id,
                e.department_id,
                e.job_id,
                e.user_id,
                DATE(a.check_in AT TIME ZONE 'UTC' AT TIME ZONE COALESCE(u.tz, 'UTC')) AS date,
                a.shift_id,
                a.check_in,
                a.check_out,
                a.worked_hours,
                a.is_late,
                a.is_early_leave,
                a.late_minutes,
                a.early_leave_minutes,
                a.attendance_type,
                a.state,
                a.check_in_method,
                a.check_out_method,
                a.company_id,
                EXTRACT(DOW FROM DATE(a.check_in AT TIME ZONE 'UTC' AT TIME ZONE COALESCE(u.tz, 'UTC'))) IN (0, 6) AS is_weekend,
                EXISTS (
                    SELECT 1 FROM vietnam_attendance_holiday h 
                    WHERE h.date = DATE(a.check_in AT TIME ZONE 'UTC' AT TIME ZONE COALESCE(u.tz, 'UTC'))
                      AND (h.company_id = a.company_id OR h.company_id IS NULL)
                ) AS is_holiday
        """
    
    def _from(self):
        return """
            FROM vietnam_attendance a
            LEFT JOIN hr_employee e ON a.employee_id = e.id
            LEFT JOIN res_users u ON e.user_id = u.id
        """
    
    def _where(self):
        return """
            WHERE a.check_in IS NOT NULL
        """
    
    def _group_by(self):
        return """
            GROUP BY
                a.id,
                a.name,
                a.employee_id,
                e.department_id,
                e.job_id,
                e.user_id,
                date,
                a.shift_id,
                a.check_in,
                a.check_out,
                a.worked_hours,
                a.is_late,
                a.is_early_leave,
                a.late_minutes,
                a.early_leave_minutes,
                a.attendance_type,
                a.state,
                a.check_in_method,
                a.check_out_method,
                a.company_id,
                is_weekend,
                u.tz
        """
    
    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                %s
                %s
                %s
                %s
            )
        """ % (self._table, self._select(), self._from(), self._where(), self._group_by())
        )
    
    @api.model
    def get_attendance_statistics(self, date_from, date_to, employee_ids=None, department_ids=None):
        """
        Lấy thống kê chấm công
        """
        domain = [
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ]
        
        if employee_ids:
            domain.append(('employee_id', 'in', employee_ids))
        
        if department_ids:
            domain.append(('department_id', 'in', department_ids))
        
        reports = self.search(domain)
        
        # Tính toán tổng hợp
        total_worked_hours = sum(reports.mapped('worked_hours'))
        late_count = len(reports.filtered(lambda r: r.is_late))
        early_leave_count = len(reports.filtered(lambda r: r.is_early_leave))
        total_late_minutes = sum(reports.mapped('late_minutes'))
        total_early_leave_minutes = sum(reports.mapped('early_leave_minutes'))
        
        # Thống kê theo nhân viên
        employee_stats = {}
        for report in reports:
            employee_id = report.employee_id.id
            if employee_id not in employee_stats:
                employee_stats[employee_id] = {
                    'employee_id': employee_id,
                    'employee_name': report.employee_id.name,
                    'department': report.department_id.name if report.department_id else '',
                    'worked_hours': 0,
                    'late_count': 0,
                    'early_leave_count': 0,
                    'late_minutes': 0,
                    'early_leave_minutes': 0,
                }
            
            employee_stats[employee_id]['worked_hours'] += report.worked_hours
            
            if report.is_late:
                employee_stats[employee_id]['late_count'] += 1
                employee_stats[employee_id]['late_minutes'] += report.late_minutes
            
            if report.is_early_leave:
                employee_stats[employee_id]['early_leave_count'] += 1
                employee_stats[employee_id]['early_leave_minutes'] += report.early_leave_minutes
        
        # Thống kê theo phòng ban
        department_stats = {}
        for report in reports:
            department_id = report.department_id.id if report.department_id else 0
            if department_id not in department_stats:
                department_stats[department_id] = {
                    'department_id': department_id,
                    'department_name': report.department_id.name if report.department_id else 'Không có phòng ban',
                    'worked_hours': 0,
                    'late_count': 0,
                    'early_leave_count': 0,
                    'late_minutes': 0,
                    'early_leave_minutes': 0,
                    'employee_count': 0,
                }
            
            department_stats[department_id]['worked_hours'] += report.worked_hours
            
            if report.is_late:
                department_stats[department_id]['late_count'] += 1
                department_stats[department_id]['late_minutes'] += report.late_minutes
            
            if report.is_early_leave:
                department_stats[department_id]['early_leave_count'] += 1
                department_stats[department_id]['early_leave_minutes'] += report.early_leave_minutes
        
        # Cập nhật số lượng nhân viên cho mỗi phòng ban
        for department_id in department_stats:
            department_stats[department_id]['employee_count'] = len(set(reports.filtered(
                lambda r: r.department_id.id == department_id if department_id else not r.department_id
            ).mapped('employee_id.id')))
        
        return {
            'date_from': date_from,
            'date_to': date_to,
            'total_worked_hours': total_worked_hours,
            'late_count': late_count,
            'early_leave_count': early_leave_count,
            'total_late_minutes': total_late_minutes,
            'total_early_leave_minutes': total_early_leave_minutes,
            'employee_stats': list(employee_stats.values()),
            'department_stats': list(department_stats.values()),
        }