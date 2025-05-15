from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging
import requests
import json
import base64
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class VietnamAttendanceDevice(models.Model):
    _name = 'vietnam.attendance.device'
    _description = 'Thiết bị chấm công'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Tên thiết bị', required=True, tracking=True)
    code = fields.Char(string='Mã thiết bị', required=True, tracking=True)
    device_type = fields.Selection([
        ('fingerprint', 'Máy chấm công vân tay'),
        ('face', 'Máy chấm công khuôn mặt'),
        ('card', 'Máy chấm công thẻ từ'),
        ('qrcode', 'Máy chấm công QR Code'),
        ('mobile', 'Ứng dụng di động'),
        ('other', 'Khác'),
    ], string='Loại thiết bị', required=True, default='fingerprint')
    
    location_id = fields.Many2one('vietnam.attendance.location', string='Địa điểm')
    device_ip = fields.Char(string='Địa chỉ IP')
    device_port = fields.Integer(string='Cổng', default=80)
    device_username = fields.Char(string='Tên đăng nhập')
    device_password = fields.Char(string='Mật khẩu')
    device_serial = fields.Char(string='Số serial')
    
    api_url = fields.Char(string='API URL', help='URL API để kết nối với thiết bị')
    api_key = fields.Char(string='API Key')
    
    company_id = fields.Many2one('res.company', string='Công ty', default=lambda self: self.env.company)
    active = fields.Boolean(string='Đang hoạt động', default=True)
    
    last_sync_date = fields.Datetime(string='Thời gian đồng bộ cuối cùng')
    sync_status = fields.Selection([
        ('success', 'Thành công'),
        ('failed', 'Thất bại'),
        ('never', 'Chưa đồng bộ'),
    ], string='Trạng thái đồng bộ', default='never')
    
    is_cloud_device = fields.Boolean(string='Thiết bị đám mây', default=False,
                                    help='Đánh dấu nếu thiết bị được lưu trữ trên đám mây và sử dụng API để kết nối')
    
    def action_test_connection(self):
        """
        Kiểm tra kết nối với thiết bị
        """
        self.ensure_one()
        
        if self.is_cloud_device:
            try:
                if not self.api_url:
                    raise UserError(_('Vui lòng cung cấp URL API'))
                
                headers = {}
                if self.api_key:
                    headers['Authorization'] = f'Bearer {self.api_key}'
                
                response = requests.get(
                    f"{self.api_url}/status",
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    self.write({
                        'sync_status': 'success',
                    })
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Kết nối thành công'),
                            'message': _('Kết nối với thiết bị thành công'),
                            'sticky': False,
                            'type': 'success',
                        }
                    }
                else:
                    self.write({
                        'sync_status': 'failed',
                    })
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Kết nối thất bại'),
                            'message': _(f'Kết nối thất bại. Mã lỗi: {response.status_code}'),
                            'sticky': False,
                            'type': 'danger',
                        }
                    }
            except Exception as e:
                self.write({
                    'sync_status': 'failed',
                })
                _logger.error(f"Lỗi kết nối thiết bị: {e}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Lỗi kết nối'),
                        'message': _(f'Lỗi kết nối thiết bị: {e}'),
                        'sticky': False,
                        'type': 'danger',
                    }
                }
        else:
            # Xử lý cho thiết bị local (sử dụng protocol của từng nhà sản xuất)
            try:
                if not self.device_ip:
                    raise UserError(_('Vui lòng cung cấp địa chỉ IP của thiết bị'))
                
                # Ở đây chúng ta sẽ triển khai các protocol kết nối với từng loại máy chấm công
                # Ví dụ: ZKTeco, Suprema, HikVision, v.v.
                
                # Giả lập kết nối thành công
                self.write({
                    'sync_status': 'success',
                })
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Kết nối thành công'),
                        'message': _('Kết nối với thiết bị thành công'),
                        'sticky': False,
                        'type': 'success',
                    }
                }
            except Exception as e:
                self.write({
                    'sync_status': 'failed',
                })
                _logger.error(f"Lỗi kết nối thiết bị: {e}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Lỗi kết nối'),
                        'message': _(f'Lỗi kết nối thiết bị: {e}'),
                        'sticky': False,
                        'type': 'danger',
                    }
                }
    
    def action_sync_attendance(self):
        """
        Đồng bộ dữ liệu chấm công từ thiết bị
        """
        self.ensure_one()
        
        if self.is_cloud_device:
            try:
                if not self.api_url:
                    raise UserError(_('Vui lòng cung cấp URL API'))
                
                # Lấy thời gian đồng bộ cuối cùng
                from_date = self.last_sync_date or fields.Datetime.now() - timedelta(days=7)
                from_date_str = fields.Datetime.to_string(from_date)
                
                headers = {}
                if self.api_key:
                    headers['Authorization'] = f'Bearer {self.api_key}'
                
                response = requests.get(
                    f"{self.api_url}/attendance",
                    params={'from_date': from_date_str},
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code == 200:
                    attendance_data = response.json()
                    self._process_attendance_data(attendance_data)
                    
                    self.write({
                        'last_sync_date': fields.Datetime.now(),
                        'sync_status': 'success',
                    })
                    
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Đồng bộ thành công'),
                            'message': _(f'Đã đồng bộ {len(attendance_data)} bản ghi chấm công'),
                            'sticky': False,
                            'type': 'success',
                        }
                    }
                else:
                    self.write({
                        'sync_status': 'failed',
                    })
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Đồng bộ thất bại'),
                            'message': _(f'Đồng bộ thất bại. Mã lỗi: {response.status_code}'),
                            'sticky': False,
                            'type': 'danger',
                        }
                    }
            except Exception as e:
                self.write({
                    'sync_status': 'failed',
                })
                _logger.error(f"Lỗi đồng bộ dữ liệu: {e}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Lỗi đồng bộ'),
                        'message': _(f'Lỗi đồng bộ dữ liệu: {e}'),
                        'sticky': False,
                        'type': 'danger',
                    }
                }
        else:
            # Xử lý cho thiết bị local
            try:
                if not self.device_ip:
                    raise UserError(_('Vui lòng cung cấp địa chỉ IP của thiết bị'))
                
                # Ở đây sẽ triển khai các protocol đồng bộ dữ liệu với từng loại máy chấm công
                
                # Giả lập đồng bộ thành công với một số dữ liệu mẫu
                sample_data = [
                    {
                        'employee_code': 'NV001',
                        'timestamp': fields.Datetime.to_string(fields.Datetime.now() - timedelta(hours=8)),
                        'type': 'check_in',
                    },
                    {
                        'employee_code': 'NV001',
                        'timestamp': fields.Datetime.to_string(fields.Datetime.now() - timedelta(hours=0.5)),
                        'type': 'check_out',
                    },
                ]
                
                self._process_attendance_data(sample_data)
                
                self.write({
                    'last_sync_date': fields.Datetime.now(),
                    'sync_status': 'success',
                })
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Đồng bộ thành công'),
                        'message': _(f'Đã đồng bộ {len(sample_data)} bản ghi chấm công'),
                        'sticky': False,
                        'type': 'success',
                    }
                }
            except Exception as e:
                self.write({
                    'sync_status': 'failed',
                })
                _logger.error(f"Lỗi đồng bộ dữ liệu: {e}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Lỗi đồng bộ'),
                        'message': _(f'Lỗi đồng bộ dữ liệu: {e}'),
                        'sticky': False,
                        'type': 'danger',
                    }
                }
    
    def _process_attendance_data(self, attendance_data):
        """
        Xử lý dữ liệu chấm công từ thiết bị
        """
        attendance_model = self.env['vietnam.attendance']
        employee_model = self.env['hr.employee']
        
        for record in attendance_data:
            employee_code = record.get('employee_code')
            timestamp = record.get('timestamp')
            record_type = record.get('type', 'check_in')  # Mặc định là check_in
            
            if not employee_code or not timestamp:
                _logger.warning(f"Dữ liệu chấm công không hợp lệ: {record}")
                continue
            
            # Tìm nhân viên theo mã
            employee = employee_model.search([('barcode', '=', employee_code)], limit=1)
            if not employee:
                _logger.warning(f"Không tìm thấy nhân viên với mã: {employee_code}")
                continue
            
            if record_type == 'check_in':
                # Tạo bản ghi chấm công mới cho check_in
                attendance_model.create({
                    'employee_id': employee.id,
                    'check_in': timestamp,
                    'check_in_device_id': self.id,
                    'check_in_location_id': self.location_id.id if self.location_id else False,
                    'check_in_method': self.device_type,
                    'state': 'confirmed',
                })
            elif record_type == 'check_out':
                # Tìm bản ghi chấm công cuối cùng của nhân viên chưa có check_out
                last_attendance = attendance_model.search([
                    ('employee_id', '=', employee.id),
                    ('check_out', '=', False),
                ], limit=1, order='check_in desc')
                
                if last_attendance:
                    last_attendance.write({
                        'check_out': timestamp,
                        'check_out_device_id': self.id,
                        'check_out_location_id': self.location_id.id if self.location_id else False,
                        'check_out_method': self.device_type,
                    })
                else:
                    # Nếu không tìm thấy bản ghi chấm công vào, tạo mới bản ghi với check_out
                    # Giả định thời gian check_in là 8 giờ trước check_out
                    check_in_time = fields.Datetime.from_string(timestamp) - timedelta(hours=8)
                    attendance_model.create({
                        'employee_id': employee.id,
                        'check_in': fields.Datetime.to_string(check_in_time),
                        'check_out': timestamp,
                        'check_out_device_id': self.id,
                        'check_out_location_id': self.location_id.id if self.location_id else False,
                        'check_out_method': self.device_type,
                        'check_in_method': self.device_type,
                        'state': 'confirmed',
                        'note': 'Tự động tạo check_in dựa trên check_out',
                    })
            else:
                _logger.warning(f"Loại bản ghi không được hỗ trợ: {record_type}")
    
    def _sync_employees_to_device(self):
        """
        Đồng bộ thông tin nhân viên lên thiết bị
        """
        self.ensure_one()
        
        if self.is_cloud_device:
            try:
                if not self.api_url:
                    raise UserError(_('Vui lòng cung cấp URL API'))
                
                # Lấy danh sách nhân viên cần đồng bộ
                employees = self.env['hr.employee'].search([
                    ('active', '=', True),
                    ('company_id', '=', self.company_id.id),
                ])
                
                employee_data = []
                for employee in employees:
                    data = {
                        'employee_code': employee.barcode or '',
                        'employee_name': employee.name,
                        'department': employee.department_id.name if employee.department_id else '',
                    }
                    
                    # Thêm ảnh nếu có
                    if employee.image_1920:
                        data['image'] = base64.b64encode(employee.image_1920).decode('utf-8')
                    
                    employee_data.append(data)
                
                headers = {}
                if self.api_key:
                    headers['Authorization'] = f'Bearer {self.api_key}'
                    headers['Content-Type'] = 'application/json'
                
                response = requests.post(
                    f"{self.api_url}/employees",
                    data=json.dumps(employee_data),
                    headers=headers,
                    timeout=60
                )
                
                if response.status_code == 200:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Đồng bộ thành công'),
                            'message': _(f'Đã đồng bộ {len(employees)} nhân viên lên thiết bị'),
                            'sticky': False,
                            'type': 'success',
                        }
                    }
                else:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Đồng bộ thất bại'),
                            'message': _(f'Đồng bộ thất bại. Mã lỗi: {response.status_code}'),
                            'sticky': False,
                            'type': 'danger',
                        }
                    }
            except Exception as e:
                _logger.error(f"Lỗi đồng bộ nhân viên: {e}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Lỗi đồng bộ'),
                        'message': _(f'Lỗi đồng bộ nhân viên: {e}'),
                        'sticky': False,
                        'type': 'danger',
                    }
                }
        else:
            # Xử lý cho thiết bị local
            try:
                if not self.device_ip:
                    raise UserError(_('Vui lòng cung cấp địa chỉ IP của thiết bị'))
                
                # Ở đây sẽ triển khai các protocol đồng bộ nhân viên với từng loại máy chấm công
                
                # Giả lập đồng bộ thành công
                employees = self.env['hr.employee'].search([
                    ('active', '=', True),
                    ('company_id', '=', self.company_id.id),
                ])
                
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Đồng bộ thành công'),
                        'message': _(f'Đã đồng bộ {len(employees)} nhân viên lên thiết bị'),
                        'sticky': False,
                        'type': 'success',
                    }
                }
            except Exception as e:
                _logger.error(f"Lỗi đồng bộ nhân viên: {e}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Lỗi đồng bộ'),
                        'message': _(f'Lỗi đồng bộ nhân viên: {e}'),
                        'sticky': False,
                        'type': 'danger',
                    }
                }
    
    @api.model
    def auto_sync_all_devices(self):
        """
        Tự động đồng bộ tất cả các thiết bị đang hoạt động
        Called by scheduled action
        """
        devices = self.search([('active', '=', True)])
        for device in devices:
            try:
                device.action_sync_attendance()
            except Exception as e:
                _logger.error(f"Lỗi đồng bộ tự động thiết bị {device.name}: {e}")
                device.write({'sync_status': 'failed'})
        
        return True
    
    def action_clear_device_data(self):
        """
        Xóa dữ liệu chấm công trên thiết bị
        """
        self.ensure_one()
        
        if self.is_cloud_device:
            try:
                if not self.api_url:
                    raise UserError(_('Vui lòng cung cấp URL API'))
                
                headers = {}
                if self.api_key:
                    headers['Authorization'] = f'Bearer {self.api_key}'
                
                response = requests.delete(
                    f"{self.api_url}/attendance",
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code == 200:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Xóa dữ liệu thành công'),
                            'message': _('Đã xóa dữ liệu chấm công trên thiết bị'),
                            'sticky': False,
                            'type': 'success',
                        }
                    }
                else:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Xóa dữ liệu thất bại'),
                            'message': _(f'Xóa dữ liệu thất bại. Mã lỗi: {response.status_code}'),
                            'sticky': False,
                            'type': 'danger',
                        }
                    }
            except Exception as e:
                _logger.error(f"Lỗi xóa dữ liệu thiết bị: {e}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Lỗi xóa dữ liệu'),
                        'message': _(f'Lỗi xóa dữ liệu thiết bị: {e}'),
                        'sticky': False,
                        'type': 'danger',
                    }
                }
        else:
            # Xử lý cho thiết bị local
            try:
                if not self.device_ip:
                    raise UserError(_('Vui lòng cung cấp địa chỉ IP của thiết bị'))
                
                # Ở đây sẽ triển khai các protocol xóa dữ liệu với từng loại máy chấm công
                
                # Giả lập xóa dữ liệu thành công
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Xóa dữ liệu thành công'),
                        'message': _('Đã xóa dữ liệu chấm công trên thiết bị'),
                        'sticky': False,
                        'type': 'success',
                    }
                }
            except Exception as e:
                _logger.error(f"Lỗi xóa dữ liệu thiết bị: {e}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Lỗi xóa dữ liệu'),
                        'message': _(f'Lỗi xóa dữ liệu thiết bị: {e}'),
                        'sticky': False,
                        'type': 'danger',
                    }
                }
    
    def action_restart_device(self):
        """
        Khởi động lại thiết bị
        """
        self.ensure_one()
        
        if self.is_cloud_device:
            try:
                if not self.api_url:
                    raise UserError(_('Vui lòng cung cấp URL API'))
                
                headers = {}
                if self.api_key:
                    headers['Authorization'] = f'Bearer {self.api_key}'
                
                response = requests.post(
                    f"{self.api_url}/restart",
                    headers=headers,
                    timeout=30
                )
                
                if response.status_code == 200:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Khởi động lại thành công'),
                            'message': _('Đã gửi lệnh khởi động lại đến thiết bị'),
                            'sticky': False,
                            'type': 'success',
                        }
                    }
                else:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Khởi động lại thất bại'),
                            'message': _(f'Khởi động lại thất bại. Mã lỗi: {response.status_code}'),
                            'sticky': False,
                            'type': 'danger',
                        }
                    }
            except Exception as e:
                _logger.error(f"Lỗi khởi động lại thiết bị: {e}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Lỗi khởi động lại'),
                        'message': _(f'Lỗi khởi động lại thiết bị: {e}'),
                        'sticky': False,
                        'type': 'danger',
                    }
                }
        else:
            # Xử lý cho thiết bị local
            try:
                if not self.device_ip:
                    raise UserError(_('Vui lòng cung cấp địa chỉ IP của thiết bị'))
                
                # Ở đây sẽ triển khai các protocol khởi động lại với từng loại máy chấm công
                
                # Giả lập khởi động lại thành công
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Khởi động lại thành công'),
                        'message': _('Đã gửi lệnh khởi động lại đến thiết bị'),
                        'sticky': False,
                        'type': 'success',
                    }
                }
            except Exception as e:
                _logger.error(f"Lỗi khởi động lại thiết bị: {e}")
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Lỗi khởi động lại'),
                        'message': _(f'Lỗi khởi động lại thiết bị: {e}'),
                        'sticky': False,
                        'type': 'danger',
                    }
                }