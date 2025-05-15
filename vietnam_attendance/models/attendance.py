from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)

class VietnamAttendance(models.Model):
    _name = 'vietnam.attendance'
    _description = 'Chấm công'
    _order = 'check_in desc'
    
    name = fields.Char(string='Tên', compute='_compute_name', store=True)
    employee_id = fields.Many2one('hr.employee', string='Nhân viên', required=True)
    user_id = fields.Many2one('res.users', string='Người dùng', related='employee_id.user_id', store=True)
    department_id = fields.Many2one('hr.department', string='Phòng ban', related='employee_id.department_id', store=True)
    
    check_in = fields.Datetime(string='Giờ vào', required=True)
    check_out = fields.Datetime(string='Giờ ra')
    
    worked_hours = fields.Float(string='Số giờ làm việc', compute='_compute_worked_hours', store=True)
    
    attendance_type = fields.Selection([
        ('normal', 'Bình thường'),
        ('overtime', 'Tăng ca'),
        ('business_trip', 'Công tác'),
        ('remote', 'Làm từ xa'),
    ], string='Loại chấm công', default='normal')
    
    # Thêm trường overtime_status để khắc phục lỗi phụ thuộc
    overtime_status = fields.Selection([
        ('none', 'Không có tăng ca'),
        ('pending', 'Chờ duyệt'),
        ('approved', 'Đã duyệt'),
        ('rejected', 'Từ chối'),
    ], string='Trạng thái tăng ca', default='none')
    
    check_in_method = fields.Selection([
        ('manual', 'Thủ công'),
        ('qrcode', 'QR Code'),
        ('face', 'Khuôn mặt'),
        ('fingerprint', 'Vân tay'),
        ('card', 'Thẻ từ'),
        ('gps', 'GPS'),
        ('wifi', 'WiFi'),
    ], string='Phương thức chấm công vào', default='manual')
    
    check_out_method = fields.Selection([
        ('manual', 'Thủ công'),
        ('qrcode', 'QR Code'),
        ('face', 'Khuôn mặt'),
        ('fingerprint', 'Vân tay'),
        ('card', 'Thẻ từ'),
        ('gps', 'GPS'),
        ('wifi', 'WiFi'),
    ], string='Phương thức chấm công ra')
    
    check_in_location_id = fields.Many2one('vietnam.attendance.location', string='Địa điểm chấm công vào')
    check_out_location_id = fields.Many2one('vietnam.attendance.location', string='Địa điểm chấm công ra')
    
    shift_id = fields.Many2one('vietnam.attendance.shift', string='Ca làm việc')
    
    is_late = fields.Boolean(string='Đi muộn', compute='_compute_late_early', store=True)
    is_early_leave = fields.Boolean(string='Về sớm', compute='_compute_late_early', store=True)
    
    late_minutes = fields.Float(string='Số phút đi muộn', compute='_compute_late_early', store=True)
    early_leave_minutes = fields.Float(string='Số phút về sớm', compute='_compute_late_early', store=True)
    
    state = fields.Selection([
        ('draft', 'Nháp'),
        ('confirmed', 'Đã xác nhận'),
        ('approved', 'Đã duyệt'),
        ('rejected', 'Từ chối'),
    ], string='Trạng thái', default='draft')
    
    note = fields.Text(string='Ghi chú')
    
    company_id = fields.Many2one('res.company', string='Công ty', default=lambda self: self.env.company)
    
    @api.depends('employee_id', 'check_in')
    def _compute_name(self):
        for attendance in self:
            if attendance.employee_id and attendance.check_in:
                employee_name = attendance.employee_id.name
                check_in_date = fields.Datetime.context_timestamp(self, attendance.check_in).strftime('%d/%m/%Y %H:%M')
                attendance.name = _('Chấm công: %s - %s') % (employee_name, check_in_date)
            else:
                attendance.name = _('Chấm công mới')
    
    @api.depends('check_in', 'check_out')
    def _compute_worked_hours(self):
        for attendance in self:
            if attendance.check_in and attendance.check_out:
                delta = attendance.check_out - attendance.check_in
                attendance.worked_hours = delta.total_seconds() / 3600.0
            else:
                attendance.worked_hours = 0.0
    
    @api.depends('check_in', 'check_out', 'shift_id')
    def _compute_late_early(self):
        for attendance in self:
            attendance.is_late = False
            attendance.is_early_leave = False
            attendance.late_minutes = 0.0
            attendance.early_leave_minutes = 0.0
            
            if attendance.shift_id and attendance.check_in:
                # Kiểm tra đi muộn
                # Ví dụ: nếu giờ vào ca là 8:00, nhân viên chấm công lúc 8:15 -> đi muộn 15 phút
                check_in_time = fields.Datetime.context_timestamp(self, attendance.check_in)
                
                # Lấy giờ vào ca (shift_start_time) và chuyển đổi thành datetime để so sánh
                shift_start = attendance.shift_id.start_time
                shift_start_hour = int(shift_start.split(':')[0])
                shift_start_minute = int(shift_start.split(':')[1])
                
                check_in_date = check_in_time.date()
                shift_start_datetime = datetime.combine(
                    check_in_date,
                    datetime.min.time().replace(hour=shift_start_hour, minute=shift_start_minute)
                )
                shift_start_datetime = fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(shift_start_datetime))
                
                # Tính toán thời gian đi muộn (nếu có)
                if check_in_time > shift_start_datetime:
                    delta = check_in_time - shift_start_datetime
                    attendance.is_late = True
                    attendance.late_minutes = delta.total_seconds() / 60.0
            
            if attendance.shift_id and attendance.check_out:
                # Kiểm tra về sớm
                # Ví dụ: nếu giờ kết thúc ca là 17:00, nhân viên chấm công lúc 16:45 -> về sớm 15 phút
                check_out_time = fields.Datetime.context_timestamp(self, attendance.check_out)
                
                # Lấy giờ kết thúc ca (shift_end_time) và chuyển đổi thành datetime để so sánh
                shift_end = attendance.shift_id.end_time
                shift_end_hour = int(shift_end.split(':')[0])
                shift_end_minute = int(shift_end.split(':')[1])
                
                check_out_date = check_out_time.date()
                shift_end_datetime = datetime.combine(
                    check_out_date,
                    datetime.min.time().replace(hour=shift_end_hour, minute=shift_end_minute)
                )
                shift_end_datetime = fields.Datetime.context_timestamp(self, fields.Datetime.to_datetime(shift_end_datetime))
                
                # Tính toán thời gian về sớm (nếu có)
                if check_out_time < shift_end_datetime:
                    delta = shift_end_datetime - check_out_time
                    attendance.is_early_leave = True
                    attendance.early_leave_minutes = delta.total_seconds() / 60.0
    
    @api.constrains('check_in', 'check_out', 'employee_id')
    def _check_validity(self):
        for attendance in self:
            # Kiểm tra check_out phải sau check_in
            if attendance.check_in and attendance.check_out and attendance.check_out < attendance.check_in:
                raise ValidationError(_('Giờ ra không thể trước giờ vào'))
            
            # Kiểm tra không được chấm công chồng chéo
            if attendance.check_in and attendance.employee_id:
                overlapping = self.search([
                    ('employee_id', '=', attendance.employee_id.id),
                    ('check_in', '<=', attendance.check_in),
                    ('check_out', '>', attendance.check_in),
                    ('id', '!=', attendance.id),
                ])
                if overlapping:
                    raise ValidationError(_(
                        'Không thể tạo chấm công chồng chéo cho nhân viên %s, đã có chấm công từ %s đến %s') % (
                            attendance.employee_id.name,
                            fields.Datetime.to_string(overlapping.check_in),
                            fields.Datetime.to_string(overlapping.check_out) if overlapping.check_out else _('hiện tại')
                        )
                    )
    
    def action_confirm(self):
        for attendance in self:
            attendance.state = 'confirmed'
    
    def action_approve(self):
        for attendance in self:
            attendance.state = 'approved'
    
    def action_reject(self):
        for attendance in self:
            attendance.state = 'rejected'
    
    def action_reset_to_draft(self):
        for attendance in self:
            attendance.state = 'draft'
    
    def name_get(self):
        result = []
        for attendance in self:
            if not attendance.check_in:
                result.append((attendance.id, _('Chấm công mới')))
                continue
            
            check_in_date = fields.Datetime.context_timestamp(self, attendance.check_in).strftime('%d/%m/%Y')
            check_in_time = fields.Datetime.context_timestamp(self, attendance.check_in).strftime('%H:%M')
            
            if attendance.check_out:
                check_out_time = fields.Datetime.context_timestamp(self, attendance.check_out).strftime('%H:%M')
                name = _('%s: %s (%s-%s)') % (attendance.employee_id.name, check_in_date, check_in_time, check_out_time)
            else:
                name = _('%s: %s (%s-)') % (attendance.employee_id.name, check_in_date, check_in_time)
            
            result.append((attendance.id, name))
        
        return result