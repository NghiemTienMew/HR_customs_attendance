from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
from datetime import datetime, timedelta
import pytz
import base64
import qrcode
import io

_logger = logging.getLogger(__name__)

class HrEmployee(models.Model):
    _inherit = 'hr.employee'
    
    attendance_ids = fields.One2many('vietnam.attendance', 'employee_id', string='Chấm công')
    
    attendances_count = fields.Integer(string='Số lần chấm công', compute='_compute_attendances_count')
    overtime_count = fields.Integer(string='Số lần tăng ca', compute='_compute_overtime_count')
    
    qr_code = fields.Binary(string='Mã QR chấm công', compute='_compute_qr_code')
    qr_code_data = fields.Char(string='Dữ liệu QR', compute='_compute_qr_code')
    
    default_attendance_location_id = fields.Many2one('vietnam.attendance.location', string='Địa điểm chấm công mặc định')
    shift_ids = fields.Many2many('vietnam.attendance.shift', string='Ca làm việc')
    
    attendance_status = fields.Selection([
        ('checked_in', 'Đã chấm công vào'),
        ('checked_out', 'Đã chấm công ra'),
        ('not_checked', 'Chưa chấm công'),
    ], string='Trạng thái chấm công', compute='_compute_attendance_status')
    
    last_check_in = fields.Datetime(string='Lần cuối chấm công vào', compute='_compute_attendance_status', store=True)
    last_check_out = fields.Datetime(string='Lần cuối chấm công ra', compute='_compute_attendance_status', store=True)
    
    late_count = fields.Integer(string='Số lần đi muộn', compute='_compute_attendance_stats')
    early_leave_count = fields.Integer(string='Số lần về sớm', compute='_compute_attendance_stats')
    absent_count = fields.Integer(string='Số lần vắng mặt', compute='_compute_attendance_stats')
    
    worked_hours_month = fields.Float(string='Số giờ làm việc trong tháng', compute='_compute_attendance_stats')
    worked_hours_year = fields.Float(string='Số giờ làm việc trong năm', compute='_compute_attendance_stats')
    
    allow_check_in = fields.Boolean(string='Cho phép chấm công', compute='_compute_allow_check_in')
    
    face_image = fields.Binary(string='Ảnh khuôn mặt chấm công')
    fingerprint_data = fields.Binary(string='Dữ liệu vân tay')
    
    @api.depends('attendance_ids')
    def _compute_attendances_count(self):
        for employee in self:
            employee.attendances_count = self.env['vietnam.attendance'].search_count([
                ('employee_id', '=', employee.id)
            ])
    
    @api.depends()
    def _compute_overtime_count(self):
        for employee in self:
            employee.overtime_count = self.env['vietnam.attendance.overtime'].search_count([
                ('employee_id', '=', employee.id)
            ])
    
    @api.depends('barcode', 'id')
    def _compute_qr_code(self):
        for employee in self:
            if employee.barcode:
                # Tạo dữ liệu QR code (thêm các dữ liệu cần thiết như id, tên, ...)
                qr_data = {
                    'employee_id': employee.id,
                    'barcode': employee.barcode,
                    'timestamp': fields.Datetime.now().isoformat(),
                }
                
                # Chuyển đổi thành chuỗi JSON
                qr_data_json = json.dumps(qr_data)
                employee.qr_code_data = qr_data_json
                
                # Tạo QR code
                qr = qrcode.QRCode(
                    version=1,
                    error_correction=qrcode.constants.ERROR_CORRECT_L,
                    box_size=10,
                    border=4,
                )
                qr.add_data(qr_data_json)
                qr.make(fit=True)
                
                img = qr.make_image(fill_color="black", back_color="white")
                
                # Chuyển đổi thành dạng binary
                buffer = io.BytesIO()
                img.save(buffer, format="PNG")
                employee.qr_code = base64.b64encode(buffer.getvalue())
            else:
                employee.qr_code = False
                employee.qr_code_data = False
    
    @api.depends('attendance_ids.check_in', 'attendance_ids.check_out')
    def _compute_attendance_status(self):
        for employee in self:
            attendance = self.env['vietnam.attendance'].search([
                ('employee_id', '=', employee.id)
            ], order='check_in desc', limit=1)
            
            if attendance:
                employee.last_check_in = attendance.check_in
                employee.last_check_out = attendance.check_out
                
                if attendance.check_out:
                    employee.attendance_status = 'checked_out'
                else:
                    employee.attendance_status = 'checked_in'
            else:
                employee.last_check_in = False
                employee.last_check_out = False
                employee.attendance_status = 'not_checked'
    
    def _compute_attendance_stats(self):
        for employee in self:
            # Lấy thời gian đầu tháng và cuối tháng
            today = fields.Date.today()
            first_day_month = today.replace(day=1)
            
            # Thời gian đầu năm
            first_day_year = today.replace(month=1, day=1)
            
            # Tính số lần đi muộn
            late_count = self.env['vietnam.attendance'].search_count([
                ('employee_id', '=', employee.id),
                ('is_late', '=', True),
                ('check_in', '>=', fields.Datetime.to_string(datetime.combine(first_day_month, datetime.min.time()))),
            ])
            
            # Tính số lần về sớm
            early_leave_count = self.env['vietnam.attendance'].search_count([
                ('employee_id', '=', employee.id),
                ('is_early_leave', '=', True),
                ('check_in', '>=', fields.Datetime.to_string(datetime.combine(first_day_month, datetime.min.time()))),
            ])
            
            # Tính số lần vắng mặt (phải dựa vào lịch làm việc)
            # Đây là một tính toán phức tạp, chỉ làm đơn giản
            absent_count = 0
            
            # Tính tổng số giờ làm việc trong tháng
            month_attendances = self.env['vietnam.attendance'].search([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', fields.Datetime.to_string(datetime.combine(first_day_month, datetime.min.time()))),
            ])
            worked_hours_month = sum(month_attendances.mapped('worked_hours'))
            
            # Tính tổng số giờ làm việc trong năm
            year_attendances = self.env['vietnam.attendance'].search([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', fields.Datetime.to_string(datetime.combine(first_day_year, datetime.min.time()))),
            ])
            worked_hours_year = sum(year_attendances.mapped('worked_hours'))
            
            employee.late_count = late_count
            employee.early_leave_count = early_leave_count
            employee.absent_count = absent_count
            employee.worked_hours_month = worked_hours_month
            employee.worked_hours_year = worked_hours_year
    
    def _compute_allow_check_in(self):
        for employee in self:
            # Cho phép chấm công nếu:
            # 1. Chưa chấm công hoặc đã chấm công ra (có thể chấm công vào lại)
            # 2. Hoặc đã chấm công vào (có thể chấm công ra)
            if employee.attendance_status in ['not_checked', 'checked_out']:
                employee.allow_check_in = True
            else:
                employee.allow_check_in = True
    
    def action_view_attendances(self):
        self.ensure_one()
        return {
            'name': _('Chấm công'),
            'type': 'ir.actions.act_window',
            'res_model': 'vietnam.attendance',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
    
    def action_view_overtime(self):
        self.ensure_one()
        return {
            'name': _('Tăng ca'),
            'type': 'ir.actions.act_window',
            'res_model': 'vietnam.attendance.overtime',
            'view_mode': 'tree,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
    
    def action_check_in(self):
        """
        Chấm công vào từ giao diện
        """
        self.ensure_one()
        
        # Kiểm tra xem nhân viên đã chấm công vào chưa
        if self.attendance_status == 'checked_in':
            raise UserError(_('Bạn đã chấm công vào rồi!'))
        
        # Tạo bản ghi chấm công mới
        attendance_vals = {
            'employee_id': self.id,
            'check_in': fields.Datetime.now(),
            'check_in_method': 'manual',
            'state': 'draft',
        }
        
        # Tìm ca làm việc phù hợp
        shift = self.env['vietnam.attendance.shift'].find_matching_shift(self.id)
        if shift:
            attendance_vals['shift_id'] = shift.id
        
        # Tạo bản ghi chấm công
        attendance = self.env['vietnam.attendance'].create(attendance_vals)
        
        # Hiển thị thông báo
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Chấm công thành công'),
                'message': _('Bạn đã chấm công vào lúc %s') % fields.Datetime.now().strftime('%H:%M:%S'),
                'sticky': False,
                'type': 'success',
            }
        }
    
    def action_check_out(self):
        """
        Chấm công ra từ giao diện
        """
        self.ensure_one()
        
        # Kiểm tra xem nhân viên đã chấm công vào chưa
        if self.attendance_status != 'checked_in':
            raise UserError(_('Bạn chưa chấm công vào!'))
        
        # Tìm bản ghi chấm công cuối cùng chưa có check_out
        attendance = self.env['vietnam.attendance'].search([
            ('employee_id', '=', self.id),
            ('check_out', '=', False),
        ], limit=1, order='check_in desc')
        
        if not attendance:
            raise UserError(_('Không tìm thấy bản ghi chấm công vào!'))
        
        # Cập nhật check_out
        attendance.write({
            'check_out': fields.Datetime.now(),
            'check_out_method': 'manual',
        })
        
        # Hiển thị thông báo
        worked_hours = attendance.worked_hours
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Chấm công thành công'),
                'message': _('Bạn đã chấm công ra lúc %s. Thời gian làm việc: %.2f giờ') % (
                    fields.Datetime.now().strftime('%H:%M:%S'), worked_hours),
                'sticky': False,
                'type': 'success',
            }
        }
    
    def register_face(self, face_image):
        """
        Đăng ký khuôn mặt cho nhân viên
        """
        self.ensure_one()
        
        if not face_image:
            raise UserError(_('Không có ảnh khuôn mặt được cung cấp'))
        
        # Lưu ảnh khuôn mặt
        self.write({
            'face_image': face_image,
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Đăng ký thành công'),
                'message': _('Đã đăng ký khuôn mặt cho nhân viên %s') % self.name,
                'sticky': False,
                'type': 'success',
            }
        }
    
    def register_fingerprint(self, fingerprint_data):
        """
        Đăng ký vân tay cho nhân viên
        """
        self.ensure_one()
        
        if not fingerprint_data:
            raise UserError(_('Không có dữ liệu vân tay được cung cấp'))
        
        # Lưu dữ liệu vân tay
        self.write({
            'fingerprint_data': fingerprint_data,
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Đăng ký thành công'),
                'message': _('Đã đăng ký vân tay cho nhân viên %s') % self.name,
                'sticky': False,
                'type': 'success',
            }
        }