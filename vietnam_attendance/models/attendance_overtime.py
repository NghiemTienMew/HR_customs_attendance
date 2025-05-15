# Sửa lỗi cho model VietnamAttendanceOvertime trong attendance_overtime.py

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
from datetime import datetime, timedelta
import pytz

_logger = logging.getLogger(__name__)

class VietnamAttendanceOvertime(models.Model):
    _name = 'vietnam.attendance.overtime'
    _description = 'Tăng ca'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Tên', compute='_compute_name', store=True)
    
    employee_id = fields.Many2one('hr.employee', string='Nhân viên', required=True, tracking=True)
    department_id = fields.Many2one('hr.department', string='Phòng ban', related='employee_id.department_id', store=True)
    job_id = fields.Many2one('hr.job', string='Chức vụ', related='employee_id.job_id', store=True)
    
    date = fields.Date(string='Ngày', required=True, tracking=True, default=fields.Date.context_today)
    start_time = fields.Float(string='Giờ bắt đầu', required=True, tracking=True)
    end_time = fields.Float(string='Giờ kết thúc', required=True, tracking=True)
    
    duration = fields.Float(string='Thời gian (giờ)', compute='_compute_duration', store=True)
    
    state = fields.Selection([
        ('draft', 'Nháp'),
        ('submitted', 'Đã nộp'),
        ('approved', 'Đã duyệt'),
        ('rejected', 'Từ chối'),
        ('cancelled', 'Đã hủy'),
    ], string='Trạng thái', default='draft', tracking=True)
    
    overtime_type = fields.Selection([
        ('normal', 'Ngày thường'),
        ('weekend', 'Cuối tuần'),
        ('holiday', 'Ngày lễ'),
        ('night', 'Ca đêm'),
    ], string='Loại tăng ca', required=True, default='normal', tracking=True)
    
    reason = fields.Text(string='Lý do', required=True)
    description = fields.Text(string='Mô tả công việc')
    
    rate = fields.Float(string='Hệ số', compute='_compute_rate', store=True)
    
    # Đảm bảo rằng attendance_ids trỏ đến trường overtime_id trong vietnam.attendance
    attendance_ids = fields.One2many('vietnam.attendance', 'overtime_id', string='Dữ liệu chấm công')
    
    manager_id = fields.Many2one('hr.employee', string='Người quản lý', compute='_compute_manager', store=True)
    approver_id = fields.Many2one('res.users', string='Người duyệt')
    
    company_id = fields.Many2one('res.company', string='Công ty', default=lambda self: self.env.company)
    
    has_attendance = fields.Boolean(string='Có dữ liệu chấm công', compute='_compute_has_attendance', store=True)
    
    allow_edit = fields.Boolean(string='Cho phép sửa', compute='_compute_allow_edit')
    
    @api.depends('employee_id', 'date')
    def _compute_name(self):
        for record in self:
            if record.employee_id and record.date:
                record.name = f"Tăng ca - {record.employee_id.name} - {record.date.strftime('%d/%m/%Y')}"
            else:
                record.name = "Tăng ca mới"
    
    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        for record in self:
            if record.end_time < record.start_time:
                # Trường hợp tăng ca qua đêm
                record.duration = (24 - record.start_time) + record.end_time
            else:
                record.duration = record.end_time - record.start_time
    
    @api.depends('overtime_type')
    def _compute_rate(self):
        for record in self:
            if record.overtime_type == 'normal':
                record.rate = 1.5
            elif record.overtime_type == 'weekend':
                record.rate = 2.0
            elif record.overtime_type == 'holiday':
                record.rate = 3.0
            elif record.overtime_type == 'night':
                record.rate = 1.5 * 1.3  # 1.5 cho tăng ca thường + 0.3 cho ca đêm
            else:
                record.rate = 1.0
    
    @api.depends('employee_id')
    def _compute_manager(self):
        for record in self:
            record.manager_id = record.employee_id.parent_id
    
    @api.depends('attendance_ids')
    def _compute_has_attendance(self):
        for record in self:
            record.has_attendance = bool(record.attendance_ids)
    
    @api.depends('state')
    def _compute_allow_edit(self):
        for record in self:
            record.allow_edit = record.state in ['draft', 'submitted']
    
    @api.constrains('start_time', 'end_time')
    def _check_times(self):
        for record in self:
            if record.start_time == record.end_time:
                raise ValidationError(_('Giờ bắt đầu và giờ kết thúc không thể giống nhau'))
    
    @api.onchange('date')
    def _onchange_date(self):
        for record in self:
            # Kiểm tra xem ngày đã chọn có phải là cuối tuần hoặc ngày lễ không
            if record.date:
                # Kiểm tra cuối tuần (5 = Thứ 7, 6 = Chủ nhật)
                weekday = record.date.weekday()
                if weekday >= 5:
                    record.overtime_type = 'weekend'
                else:
                    # Kiểm tra ngày lễ
                    holiday_model = self.env['vietnam.attendance.holiday']
                    is_holiday = holiday_model.check_is_holiday(record.date, record.employee_id)
                    if is_holiday:
                        record.overtime_type = 'holiday'
                    else:
                        record.overtime_type = 'normal'
    
    def action_submit(self):
        for record in self:
            if record.state == 'draft':
                record.state = 'submitted'
                
                # Tạo hoạt động thông báo cho người quản lý
                if record.manager_id and record.manager_id.user_id:
                    record.activity_schedule(
                        'mail.mail_activity_data_todo',
                        user_id=record.manager_id.user_id.id,
                        note=f"{record.employee_id.name} đã nộp yêu cầu tăng ca.",
                        summary="Yêu cầu tăng ca cần duyệt",
                    )
    
    def action_approve(self):
        for record in self:
            if record.state == 'submitted':
                record.state = 'approved'
                record.approver_id = self.env.user.id
                
                # Hoàn thành các hoạt động liên quan
                record.activity_feedback(['mail.mail_activity_data_todo'])
                
                # Tạo dữ liệu chấm công tự động nếu được cấu hình
                config = self.env['vietnam.attendance.config'].get_config()
                if config.auto_attendance_from_trip:
                    self._create_attendance_from_overtime()
    
    def action_reject(self):
        for record in self:
            if record.state == 'submitted':
                record.state = 'rejected'
                record.approver_id = self.env.user.id
                
                # Hoàn thành các hoạt động liên quan
                record.activity_feedback(['mail.mail_activity_data_todo'])
    
    def action_cancel(self):
        for record in self:
            if record.state not in ['approved', 'rejected']:
                record.state = 'cancelled'
    
    def action_reset_to_draft(self):
        for record in self:
            if record.state in ['submitted', 'rejected', 'cancelled']:
                record.state = 'draft'
    
    def _create_attendance_from_overtime(self):
        """
        Tạo dữ liệu chấm công từ tăng ca đã được duyệt
        """
        self.ensure_one()
        
        if self.state != 'approved':
            return False
        
        # Kiểm tra xem đã có dữ liệu chấm công chưa
        if self.has_attendance:
            return False
        
        attendance_model = self.env['vietnam.attendance']
        
        # Chuyển đổi giờ sang datetime
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        
        # Tạo datetime cho giờ bắt đầu
        start_hour = int(self.start_time)
        start_minute = int((self.start_time - start_hour) * 60)
        
        start_datetime_local = datetime.combine(
            self.date,
            datetime.min.time().replace(hour=start_hour, minute=start_minute)
        )
        start_datetime_utc = tz.localize(start_datetime_local).astimezone(pytz.UTC)
        
        # Tạo datetime cho giờ kết thúc
        end_hour = int(self.end_time)
        end_minute = int((self.end_time - end_hour) * 60)
        
        # Xử lý trường hợp tăng ca qua đêm
        if self.end_time < self.start_time:
            end_date = self.date + timedelta(days=1)
        else:
            end_date = self.date
        
        end_datetime_local = datetime.combine(
            end_date,
            datetime.min.time().replace(hour=end_hour, minute=end_minute)
        )
        end_datetime_utc = tz.localize(end_datetime_local).astimezone(pytz.UTC)
        
        # Tạo bản ghi chấm công
        attendance = attendance_model.create({
            'employee_id': self.employee_id.id,
            'check_in': start_datetime_utc,
            'check_out': end_datetime_utc,
            'overtime_id': self.id,
            'attendance_type': 'overtime',
            'check_in_method': 'manual',
            'check_out_method': 'manual',
            'state': 'approved',
            'note': f"Tự động tạo từ phê duyệt tăng ca: {self.name}\nLý do: {self.reason}",
        })
        
        return attendance