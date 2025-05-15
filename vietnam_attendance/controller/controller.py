from odoo import http, _
from odoo.http import request
import json
import werkzeug
import base64
import logging
from datetime import datetime
import pytz
import qrcode
from io import BytesIO

_logger = logging.getLogger(__name__)

class VietnamAttendanceController(http.Controller):
    
    @http.route('/vietnam_attendance/check_in', type='json', auth='user')
    def check_in(self, **kw):
        """
        API endpoint cho chấm công vào từ ứng dụng di động
        """
        employee = request.env.user.employee_id
        if not employee:
            return {'success': False, 'message': _('Không tìm thấy thông tin nhân viên')}
        
        # Lấy thông tin từ client
        check_in_method = kw.get('check_in_method', 'manual')
        latitude = kw.get('latitude')
        longitude = kw.get('longitude')
        location_id = kw.get('location_id')
        device_id = kw.get('device_id')
        image = kw.get('image')
        wifi_ssid = kw.get('wifi_ssid')
        wifi_bssid = kw.get('wifi_bssid')
        
        # Tìm địa điểm phù hợp nếu có tọa độ hoặc WiFi
        if (latitude and longitude) or wifi_ssid:
            if not location_id:
                locations = request.env['vietnam.attendance.location'].find_matching_location(
                    latitude=latitude,
                    longitude=longitude,
                    ssid=wifi_ssid,
                    bssid=wifi_bssid,
                    employee=employee
                )
                if locations:
                    location_id = locations[0].id
        
        # Gọi phương thức chấm công từ mô hình
        return request.env['vietnam.attendance'].check_in_from_mobile(
            employee_id=employee.id,
            check_in_method=check_in_method,
            latitude=latitude,
            longitude=longitude,
            location_id=location_id,
            device_id=device_id,
            image=image
        )
    
    @http.route('/vietnam_attendance/check_out', type='json', auth='user')
    def check_out(self, **kw):
        """
        API endpoint cho chấm công ra từ ứng dụng di động
        """
        # Lấy thông tin từ client
        attendance_id = kw.get('attendance_id')
        check_out_method = kw.get('check_out_method', 'manual')
        latitude = kw.get('latitude')
        longitude = kw.get('longitude')
        location_id = kw.get('location_id')
        device_id = kw.get('device_id')
        image = kw.get('image')
        wifi_ssid = kw.get('wifi_ssid')
        wifi_bssid = kw.get('wifi_bssid')
        
        employee = request.env.user.employee_id
        if not employee:
            return {'success': False, 'message': _('Không tìm thấy thông tin nhân viên')}
        
        # Tìm bản ghi chấm công nếu không có attendance_id
        if not attendance_id:
            attendance = request.env['vietnam.attendance'].search([
                ('employee_id', '=', employee.id),
                ('check_out', '=', False)
            ], order='check_in desc', limit=1)
            
            if not attendance:
                return {'success': False, 'message': _('Không tìm thấy bản ghi chấm công vào')}
            
            attendance_id = attendance.id
        
        # Tìm địa điểm phù hợp nếu có tọa độ hoặc WiFi
        if (latitude and longitude) or wifi_ssid:
            if not location_id:
                locations = request.env['vietnam.attendance.location'].find_matching_location(
                    latitude=latitude,
                    longitude=longitude,
                    ssid=wifi_ssid,
                    bssid=wifi_bssid,
                    employee=employee
                )
                if locations:
                    location_id = locations[0].id
        
        # Gọi phương thức chấm công ra
        return request.env['vietnam.attendance'].check_out_from_mobile(
            attendance_id=attendance_id,
            check_out_method=check_out_method,
            latitude=latitude,
            longitude=longitude,
            location_id=location_id,
            device_id=device_id,
            image=image
        )
    
    @http.route('/vietnam_attendance/get_attendance_status', type='json', auth='user')
    def get_attendance_status(self):
        """
        API endpoint để lấy trạng thái chấm công hiện tại của nhân viên
        """
        employee = request.env.user.employee_id
        if not employee:
            return {'success': False, 'message': _('Không tìm thấy thông tin nhân viên')}
        
        # Lấy bản ghi chấm công cuối cùng
        attendance = request.env['vietnam.attendance'].search([
            ('employee_id', '=', employee.id)
        ], order='check_in desc', limit=1)
        
        if not attendance:
            return {
                'success': True,
                'status': 'not_checked',
                'message': _('Chưa có dữ liệu chấm công')
            }
        
        if attendance.check_out:
            # Đã chấm công ra
            user_tz = pytz.timezone(request.env.user.tz or 'UTC')
            check_out_local = pytz.utc.localize(attendance.check_out).astimezone(user_tz)
            
            return {
                'success': True,
                'status': 'checked_out',
                'message': _('Đã chấm công ra'),
                'attendance_id': attendance.id,
                'check_in': attendance.check_in,
                'check_out': attendance.check_out,
                'check_out_local': check_out_local.strftime('%H:%M:%S'),
                'worked_hours': attendance.worked_hours,
            }
        else:
            # Đã chấm công vào nhưng chưa chấm công ra
            user_tz = pytz.timezone(request.env.user.tz or 'UTC')
            check_in_local = pytz.utc.localize(attendance.check_in).astimezone(user_tz)
            
            return {
                'success': True,
                'status': 'checked_in',
                'message': _('Đã chấm công vào'),
                'attendance_id': attendance.id,
                'check_in': attendance.check_in,
                'check_in_local': check_in_local.strftime('%H:%M:%S'),
            }
    
    @http.route('/vietnam_attendance/get_attendance_history', type='json', auth='user')
    def get_attendance_history(self, date_from=None, date_to=None, limit=30):
        """
        API endpoint để lấy lịch sử chấm công
        """
        employee = request.env.user.employee_id
        if not employee:
            return {'success': False, 'message': _('Không tìm thấy thông tin nhân viên')}
        
        domain = [('employee_id', '=', employee.id)]
        
        if date_from:
            domain.append(('check_in', '>=', date_from))
        
        if date_to:
            domain.append(('check_in', '<=', date_to))
        
        attendances = request.env['vietnam.attendance'].search(domain, order='check_in desc', limit=limit)
        
        attendance_list = []
        user_tz = pytz.timezone(request.env.user.tz or 'UTC')
        
        for attendance in attendances:
            check_in_local = pytz.utc.localize(attendance.check_in).astimezone(user_tz) if attendance.check_in else False
            check_out_local = pytz.utc.localize(attendance.check_out).astimezone(user_tz) if attendance.check_out else False
            
            attendance_data = {
                'id': attendance.id,
                'check_in': attendance.check_in,
                'check_out': attendance.check_out,
                'check_in_local': check_in_local.strftime('%H:%M:%S') if check_in_local else False,
                'check_out_local': check_out_local.strftime('%H:%M:%S') if check_out_local else False,
                'date': check_in_local.date().isoformat() if check_in_local else False,
                'worked_hours': attendance.worked_hours,
                'state': attendance.state,
                'is_late': attendance.is_late,
                'is_early_leave': attendance.is_early_leave,
                'late_minutes': attendance.late_minutes,
                'early_leave_minutes': attendance.early_leave_minutes,
                'attendance_type': attendance.attendance_type,
            }
            
            attendance_list.append(attendance_data)
        
        return {
            'success': True,
            'attendances': attendance_list,
        }
    
    @http.route('/vietnam_attendance/get_shifts', type='json', auth='user')
    def get_shifts(self):
        """
        API endpoint để lấy danh sách ca làm việc
        """
        employee = request.env.user.employee_id
        if not employee:
            return {'success': False, 'message': _('Không tìm thấy thông tin nhân viên')}
        
        # Tìm ca làm việc cho nhân viên hoặc phòng ban
        shifts = request.env['vietnam.attendance.shift'].search([
            '|',
            ('department_ids', 'in', employee.department_id.id if employee.department_id else False),
            ('department_ids', '=', False),
            ('active', '=', True),
        ])
        
        shift_list = []
        for shift in shifts:
            shift_data = {
                'id': shift.id,
                'name': shift.name,
                'code': shift.code,
                'start_time': shift.start_time,
                'end_time': shift.end_time,
                'working_hours': shift.working_hours,
                'is_night_shift': shift.is_night_shift,
                'is_overtime_shift': shift.is_overtime_shift,
            }
            
            shift_list.append(shift_data)
        
        return {
            'success': True,
            'shifts': shift_list,
        }
    
    @http.route('/vietnam_attendance/get_locations', type='json', auth='user')
    def get_locations(self):
        """
        API endpoint để lấy danh sách địa điểm chấm công
        """
        employee = request.env.user.employee_id
        if not employee:
            return {'success': False, 'message': _('Không tìm thấy thông tin nhân viên')}
        
        # Tìm địa điểm chấm công cho nhân viên hoặc phòng ban
        locations = request.env['vietnam.attendance.location'].search([
            '|',
            ('department_ids', 'in', employee.department_id.id if employee.department_id else False),
            ('department_ids', '=', False),
            ('active', '=', True),
        ])
        
        location_list = []
        for location in locations:
            location_data = {
                'id': location.id,
                'name': location.name,
                'address': location.address,
                'latitude': location.latitude,
                'longitude': location.longitude,
                'radius': location.radius,
                'wifi_ssid': location.wifi_ssid,
                'allow_check_in': location.allow_check_in,
                'allow_check_out': location.allow_check_out,
            }
            
            location_list.append(location_data)
        
        return {
            'success': True,
            'locations': location_list,
        }
    
    @http.route('/vietnam_attendance/register_face', type='json', auth='user')
    def register_face(self, face_image):
        """
        API endpoint để đăng ký khuôn mặt
        """
        employee = request.env.user.employee_id
        if not employee:
            return {'success': False, 'message': _('Không tìm thấy thông tin nhân viên')}
        
        if not face_image:
            return {'success': False, 'message': _('Không có ảnh khuôn mặt được cung cấp')}
        
        try:
            employee.write({
                'face_image': face_image,
            })
            
            return {
                'success': True,
                'message': _('Đăng ký khuôn mặt thành công'),
            }
        except Exception as e:
            _logger.error(f"Lỗi đăng ký khuôn mặt: {e}")
            return {
                'success': False,
                'message': _(f'Lỗi đăng ký khuôn mặt: {e}'),
            }
    
    @http.route('/vietnam_attendance/get_statistics', type='json', auth='user')
    def get_statistics(self, date_from=None, date_to=None):
        """
        API endpoint để lấy thống kê chấm công
        """
        employee = request.env.user.employee_id
        if not employee:
            return {'success': False, 'message': _('Không tìm thấy thông tin nhân viên')}
        
        return request.env['vietnam.attendance'].get_attendance_analytics(
            employee_id=employee.id,
            date_from=date_from,
            date_to=date_to
        )
    
    @http.route('/vietnam_attendance/qrcode', type='http', auth='user')
    def get_qrcode(self):
        """
        Tạo mã QR cho nhân viên để chấm công
        """
        employee = request.env.user.employee_id
        if not employee:
            return werkzeug.exceptions.NotFound()
        
        # Tạo dữ liệu QR
        qr_data = {
            'employee_id': employee.id,
            'name': employee.name,
            'barcode': employee.barcode,
            'timestamp': datetime.now().isoformat(),
        }
        
        # Chuyển đổi thành chuỗi JSON
        qr_data_str = json.dumps(qr_data)
        
        # Tạo mã QR
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data_str)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Trả về ảnh PNG
        stream = BytesIO()
        img.save(stream, 'PNG')
        return request.make_response(
            stream.getvalue(),
            [('Content-Type', 'image/png')]
        )