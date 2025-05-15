from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import pytz
import logging

_logger = logging.getLogger(__name__)

class VietnamAttendance(models.Model):
    _name = 'vietnam.attendance'
    _description = 'Chấm công Việt Nam'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'check_in desc'

    name = fields.Char(string='Tên', compute='_compute_name', store=True)
    employee_id = fields.Many2one('hr.employee', string='Nhân viên', required=True, index=True)
    department_id = fields.Many2one('hr.department', string='Phòng ban', related='employee_id.department_id', store=True)
    job_id = fields.Many2one('hr.job', string='Chức vụ', related='employee_id.job_id', store=True)
    check_in = fields.Datetime(string='Giờ vào', required=True, default=fields.Datetime.now)
    check_out = fields.Datetime(string='Giờ ra')
    check_in_device_id = fields.Many2one('vietnam.attendance.device', string='Thiết bị chấm công vào')
    check_out_device_id = fields.Many2one('vietnam.attendance.device', string='Thiết bị chấm công ra')
    worked_hours = fields.Float(string='Số giờ làm việc', compute='_compute_worked_hours', store=True)
    shift_id = fields.Many2one('vietnam.attendance.shift', string='Ca làm việc')
    
    state = fields.Selection([
        ('draft', 'Nháp'),
        ('confirmed', 'Đã xác nhận'),
        ('approved', 'Đã duyệt'),
        ('rejected', 'Từ chối'),
    ], string='Trạng thái', default='draft', tracking=True)
    
    is_late = fields.Boolean(string='Đi muộn', compute='_compute_attendance_status', store=True)
    is_early_leave = fields.Boolean(string='Về sớm', compute='_compute_attendance_status', store=True)
    late_minutes = fields.Float(string='Số phút đi muộn', compute='_compute_attendance_status', store=True)
    early_leave_minutes = fields.Float(string='Số phút về sớm', compute='_compute_attendance_status', store=True)
    
    attendance_type = fields.Selection([
        ('normal', 'Bình thường'),
        ('overtime', 'Tăng ca'),
        ('business_trip', 'Công tác'),
        ('remote', 'Làm từ xa'),
    ], string='Loại chấm công', default='normal', required=True, tracking=True)
    
    # Thêm trường overtime_status để giải quyết lỗi
    overtime_status = fields.Selection([
        ('pending', 'Chờ duyệt'),
        ('approved', 'Đã duyệt'),
        ('rejected', 'Từ chối'),
        ('not_applicable', 'Không áp dụng'),
    ], string='Trạng thái tăng ca', default='not_applicable', compute='_compute_overtime_status', store=True)
    
    check_in_location_id = fields.Many2one('vietnam.attendance.location', string='Địa điểm chấm công vào')
    check_out_location_id = fields.Many2one('vietnam.attendance.location', string='Địa điểm chấm công ra')
    check_in_latitude = fields.Float(string='Vĩ độ chấm công vào', digits=(10, 7))
    check_in_longitude = fields.Float(string='Kinh độ chấm công vào', digits=(10, 7))
    check_out_latitude = fields.Float(string='Vĩ độ chấm công ra', digits=(10, 7))
    check_out_longitude = fields.Float(string='Kinh độ chấm công ra', digits=(10, 7))
    
    check_in_method = fields.Selection([
        ('manual', 'Thủ công'),
        ('qrcode', 'QR Code'),
        ('face', 'Khuôn mặt'),
        ('fingerprint', 'Vân tay'),
        ('card', 'Thẻ từ'),
        ('gps', 'GPS'),
        ('wifi', 'WiFi'),
    ], string='Phương thức chấm công vào', default='manual', required=True)
    
    check_out_method = fields.Selection([
        ('manual', 'Thủ công'),
        ('qrcode', 'QR Code'),
        ('face', 'Khuôn mặt'),
        ('fingerprint', 'Vân tay'),
        ('card', 'Thẻ từ'),
        ('gps', 'GPS'),
        ('wifi', 'WiFi'),
    ], string='Phương thức chấm công ra', default='manual')
    
    note = fields.Text(string='Ghi chú')
    image_in = fields.Binary(string='Ảnh chấm công vào')
    image_out = fields.Binary(string='Ảnh chấm công ra')
    
    leave_id = fields.Many2one('hr.leave', string='Nghỉ phép liên quan')
    overtime_id = fields.Many2one('vietnam.attendance.overtime', string='Tăng ca liên quan')
    
    company_id = fields.Many2one('res.company', string='Công ty', default=lambda self: self.env.company)
    
    @api.depends('employee_id', 'check_in')
    def _compute_name(self):
        for record in self:
            check_in_local = fields.Datetime.context_timestamp(self, record.check_in) if record.check_in else False
            check_in_str = check_in_local.strftime('%d/%m/%Y %H:%M:%S') if check_in_local else ''
            record.name = f"{record.employee_id.name} - {check_in_str}" if record.employee_id else ''
    
    @api.depends('check_in', 'check_out')
    def _compute_worked_hours(self):
        for attendance in self:
            if attendance.check_in and attendance.check_out:
                delta = attendance.check_out - attendance.check_in
                attendance.worked_hours = delta.total_seconds() / 3600.0
            else:
                attendance.worked_hours = 0.0
    
    @api.depends('attendance_type', 'overtime_id', 'overtime_id.state')
    def _compute_overtime_status(self):
        for attendance in self:
            if attendance.attendance_type == 'overtime' and attendance.overtime_id:
                if attendance.overtime_id.state == 'approved':
                    attendance.overtime_status = 'approved'
                elif attendance.overtime_id.state == 'rejected':
                    attendance.overtime_status = 'rejected'
                else:
                    attendance.overtime_status = 'pending'
            else:
                attendance.overtime_status = 'not_applicable'
    
    @api.depends('check_in', 'check_out', 'shift_id')
    def _compute_attendance_status(self):
        for attendance in self:
            attendance.is_late = False
            attendance.is_early_leave = False
            attendance.late_minutes = 0.0
            attendance.early_leave_minutes = 0.0
            
            if attendance.shift_id and attendance.check_in:
                # Chuyển múi giờ sang giờ địa phương
                tz = pytz.timezone(self.env.user.tz or 'UTC')
                check_in_local = pytz.utc.localize(attendance.check_in).astimezone(tz)
                
                # Tạo đối tượng datetime cho thời gian bắt đầu ca
                shift_start_time = attendance.shift_id.start_time
                shift_start_hour = int(shift_start_time)
                shift_start_minute = int((shift_start_time - shift_start_hour) * 60)
                
                shift_start_datetime = check_in_local.replace(
                    hour=shift_start_hour,
                    minute=shift_start_minute,
                    second=0,
                    microsecond=0
                )
                
                # Nếu thời gian chấm công vào muộn hơn thời gian bắt đầu ca
                if check_in_local > shift_start_datetime:
                    delta = check_in_local - shift_start_datetime
                    attendance.is_late = True
                    attendance.late_minutes = delta.total_seconds() / 60.0
            
            if attendance.shift_id and attendance.check_out:
                # Chuyển múi giờ sang giờ địa phương
                tz = pytz.timezone(self.env.user.tz or 'UTC')
                check_out_local = pytz.utc.localize(attendance.check_out).astimezone(tz)
                
                # Tạo đối tượng datetime cho thời gian kết thúc ca
                shift_end_time = attendance.shift_id.end_time
                shift_end_hour = int(shift_end_time)
                shift_end_minute = int((shift_end_time - shift_end_hour) * 60)
                
                shift_end_datetime = check_out_local.replace(
                    hour=shift_end_hour,
                    minute=shift_end_minute,
                    second=0,
                    microsecond=0
                )
                
                # Nếu thời gian chấm công ra sớm hơn thời gian kết thúc ca
                if check_out_local < shift_end_datetime:
                    delta = shift_end_datetime - check_out_local
                    attendance.is_early_leave = True
                    attendance.early_leave_minutes = delta.total_seconds() / 60.0
    
    @api.constrains('check_in', 'check_out')
    def _check_validity_check_in_check_out(self):
        for attendance in self:
            if attendance.check_in and attendance.check_out:
                if attendance.check_out < attendance.check_in:
                    raise ValidationError(_('Thời gian chấm công ra phải lớn hơn thời gian chấm công vào'))
    
    @api.constrains('check_in', 'check_out', 'employee_id')
    def _check_overlapping_attendance(self):
        for attendance in self:
            if attendance.check_in and attendance.employee_id:
                domain = [
                    ('employee_id', '=', attendance.employee_id.id),
                    ('id', '!=', attendance.id),
                    ('check_in', '<=', attendance.check_in),
                    '|', ('check_out', '>=', attendance.check_in), ('check_out', '=', False)
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(_('Có sự chồng chéo với dữ liệu chấm công hiện có.'))
    
    def action_confirm(self):
        for record in self:
            record.state = 'confirmed'
    
    def action_approve(self):
        for record in self:
            record.state = 'approved'
    
    def action_reject(self):
        for record in self:
            record.state = 'rejected'
    
    def action_reset_to_draft(self):
        for record in self:
            record.state = 'draft'
    
    def check_in_from_mobile(self, employee_id, check_in_method, latitude=None, longitude=None, location_id=None, device_id=None, image=None):
        """
        API endpoint for mobile check-in
        """
        employee = self.env['hr.employee'].browse(employee_id)
        if not employee:
            return {'success': False, 'message': 'Không tìm thấy nhân viên'}
        
        # Tạo bản ghi chấm công mới
        values = {
            'employee_id': employee.id,
            'check_in': fields.Datetime.now(),
            'check_in_method': check_in_method,
            'state': 'confirmed',  # Tự động xác nhận khi chấm công từ thiết bị
        }
        
        if latitude and longitude:
            values.update({
                'check_in_latitude': latitude,
                'check_in_longitude': longitude,
            })
        
        if location_id:
            values.update({
                'check_in_location_id': location_id,
            })
        
        if device_id:
            values.update({
                'check_in_device_id': device_id,
            })
        
        if image:
            values.update({
                'image_in': image,
            })
        
        # Tìm ca làm việc phù hợp
        shift = self.env['vietnam.attendance.shift'].find_matching_shift(employee.id)
        if shift:
            values.update({
                'shift_id': shift.id,
            })
        
        attendance = self.create(values)
        
        return {
            'success': True,
            'attendance_id': attendance.id,
            'message': 'Chấm công vào thành công'
        }
    
    def check_out_from_mobile(self, attendance_id, check_out_method, latitude=None, longitude=None, location_id=None, device_id=None, image=None):
        """
        API endpoint for mobile check-out
        """
        attendance = self.browse(attendance_id)
        if not attendance:
            return {'success': False, 'message': 'Không tìm thấy dữ liệu chấm công'}
        
        if attendance.check_out:
            return {'success': False, 'message': 'Bạn đã chấm công ra rồi'}
        
        values = {
            'check_out': fields.Datetime.now(),
            'check_out_method': check_out_method,
        }
        
        if latitude and longitude:
            values.update({
                'check_out_latitude': latitude,
                'check_out_longitude': longitude,
            })
        
        if location_id:
            values.update({
                'check_out_location_id': location_id,
            })
        
        if device_id:
            values.update({
                'check_out_device_id': device_id,
            })
        
        if image:
            values.update({
                'image_out': image,
            })
        
        attendance.write(values)
        
        return {
            'success': True,
            'message': 'Chấm công ra thành công',
            'worked_hours': attendance.worked_hours
        }
    
    def get_attendance_analytics(self, employee_id, date_from, date_to):
        """
        API endpoint to get attendance analytics
        """
        employee = self.env['hr.employee'].browse(employee_id)
        if not employee:
            return {'success': False, 'message': 'Không tìm thấy nhân viên'}
        
        date_from = fields.Date.from_string(date_from)
        date_to = fields.Date.from_string(date_to)
        
        domain = [
            ('employee_id', '=', employee.id),
            ('check_in', '>=', fields.Datetime.to_string(datetime.combine(date_from, datetime.min.time()))),
            ('check_in', '<=', fields.Datetime.to_string(datetime.combine(date_to, datetime.max.time()))),
        ]
        
        attendances = self.search(domain)
        
        total_worked_hours = sum(attendances.mapped('worked_hours'))
        late_count = len(attendances.filtered(lambda a: a.is_late))
        early_leave_count = len(attendances.filtered(lambda a: a.is_early_leave))
        
        return {
            'success': True,
            'employee_name': employee.name,
            'date_from': date_from,
            'date_to': date_to,
            'total_worked_hours': total_worked_hours,
            'late_count': late_count,
            'early_leave_count': early_leave_count,
            'attendance_count': len(attendances),
        }