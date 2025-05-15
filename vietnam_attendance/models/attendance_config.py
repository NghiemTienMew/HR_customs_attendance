from odoo import models, fields, api, _
from odoo.exceptions import UserError

class VietnamAttendanceConfig(models.Model):
    _name = 'vietnam.attendance.config'
    _description = 'Cấu hình chấm công'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Tên', required=True, default="Cấu hình chấm công", tracking=True)
    company_id = fields.Many2one('res.company', string='Công ty', default=lambda self: self.env.company)
    active = fields.Boolean(string='Đang hoạt động', default=True)
    
    # Tính năng chấm công
    allow_qrcode = fields.Boolean(string='Cho phép chấm công QR Code', default=True)
    allow_face_recognition = fields.Boolean(string='Cho phép chấm công khuôn mặt', default=True)
    allow_gps = fields.Boolean(string='Cho phép chấm công GPS', default=True)
    allow_wifi = fields.Boolean(string='Cho phép chấm công WiFi', default=True)
    allow_fingerprint = fields.Boolean(string='Cho phép chấm công vân tay', default=True)
    allow_manual = fields.Boolean(string='Cho phép chấm công thủ công', default=True)
    
    # Tính năng GPS
    gps_accuracy = fields.Float(string='Độ chính xác GPS (mét)', default=100.0)
    
    # Cấu hình WiFi
    allowed_wifi_networks = fields.Text(string='Danh sách WiFi cho phép', 
                                       help='Danh sách SSID của các mạng WiFi được phép chấm công, mỗi dòng 1 SSID')
    
    # Cấu hình tự động
    auto_check_out = fields.Boolean(string='Tự động tạo check-out', default=False,
                                    help='Tự động tạo check-out cho các bản ghi chấm công chưa có check-out')
    auto_check_out_time = fields.Float(string='Thời gian tự động check-out', default=17.5,
                                      help='Giờ tự động tạo check-out (ví dụ: 17.5 = 17:30)')
    
    # Cấu hình thông báo
    notify_manager_on_late = fields.Boolean(string='Thông báo quản lý khi nhân viên đi muộn', default=True)
    notify_manager_on_early_leave = fields.Boolean(string='Thông báo quản lý khi nhân viên về sớm', default=True)
    notify_employee_on_missing_check = fields.Boolean(string='Thông báo nhân viên khi thiếu chấm công', default=True)
    
    # Cấu hình làm thêm giờ
    overtime_approval_required = fields.Boolean(string='Yêu cầu phê duyệt tăng ca', default=True)
    overtime_minimum_hours = fields.Float(string='Thời gian tăng ca tối thiểu (giờ)', default=1.0)
    
    # Cấu hình chấm công tự động từ nghỉ phép và công tác
    auto_attendance_from_leave = fields.Boolean(string='Tự động tạo chấm công từ nghỉ phép', default=True)
    auto_attendance_from_trip = fields.Boolean(string='Tự động tạo chấm công từ công tác', default=True)
    
    # Cấu hình đồng bộ
    sync_interval = fields.Integer(string='Thời gian đồng bộ (phút)', default=15,
                                 help='Thời gian giữa các lần đồng bộ dữ liệu từ máy chấm công')
    
    # Cấu hình báo cáo
    default_report_type = fields.Selection([
        ('daily', 'Báo cáo hàng ngày'),
        ('weekly', 'Báo cáo hàng tuần'),
        ('monthly', 'Báo cáo hàng tháng'),
    ], string='Loại báo cáo mặc định', default='monthly')
    
    @api.model
    def get_config(self, company_id=None):
        """
        Lấy cấu hình chấm công theo công ty
        """
        if not company_id:
            company_id = self.env.company.id
        
        config = self.search([('company_id', '=', company_id), ('active', '=', True)], limit=1)
        if not config:
            # Tạo cấu hình mặc định nếu chưa có
            config = self.create({
                'name': f"Cấu hình chấm công - {self.env.company.name}",
                'company_id': company_id,
            })
        
        return config
    
    def execute_auto_check_out(self):
        """
        Tự động tạo check-out cho các bản ghi chấm công chưa có check-out
        """
        if not self.auto_check_out:
            return
        
        attendance_model = self.env['vietnam.attendance']
        
        # Tìm các bản ghi chấm công chưa có check-out của ngày hôm trước
        yesterday = fields.Date.today() - fields.Datetime.timedelta(days=1)
        yesterday_start = fields.Datetime.to_string(fields.Datetime.from_string(f"{yesterday} 00:00:00"))
        yesterday_end = fields.Datetime.to_string(fields.Datetime.from_string(f"{yesterday} 23:59:59"))
        
        attendances_without_checkout = attendance_model.search([
            ('check_in', '>=', yesterday_start),
            ('check_in', '<=', yesterday_end),
            ('check_out', '=', False),
            ('company_id', '=', self.company_id.id),
        ])
        
        # Tạo check-out tự động
        for attendance in attendances_without_checkout:
            # Lấy ngày từ check-in
            check_in_date = attendance.check_in.date()
            
            # Tạo datetime cho check-out từ ngày check-in và giờ auto_check_out_time
            auto_check_out_hour = int(self.auto_check_out_time)
            auto_check_out_minute = int((self.auto_check_out_time - auto_check_out_hour) * 60)
            
            check_out_datetime = fields.Datetime.from_string(
                f"{check_in_date} {auto_check_out_hour:02d}:{auto_check_out_minute:02d}:00"
            )
            
            # Cập nhật check-out
            attendance.write({
                'check_out': fields.Datetime.to_string(check_out_datetime),
                'check_out_method': 'manual',
                'note': f"{attendance.note or ''}\nCheck-out tự động tạo bởi hệ thống.",
            })
        
        return True
    
    def send_missing_check_notifications(self):
        """
        Gửi thông báo khi thiếu chấm công
        """
        if not self.notify_employee_on_missing_check:
            return
        
        attendance_model = self.env['vietnam.attendance']
        employee_model = self.env['hr.employee']
        
        # Tìm nhân viên đang làm việc
        active_employees = employee_model.search([
            ('active', '=', True),
            ('company_id', '=', self.company_id.id),
        ])
        
        # Lấy ngày hôm qua
        yesterday = fields.Date.today() - fields.Datetime.timedelta(days=1)
        yesterday_start = fields.Datetime.to_string(fields.Datetime.from_string(f"{yesterday} 00:00:00"))
        yesterday_end = fields.Datetime.to_string(fields.Datetime.from_string(f"{yesterday} 23:59:59"))
        
        # Kiểm tra từng nhân viên
        for employee in active_employees:
            # Đếm số bản ghi chấm công của nhân viên trong ngày hôm qua
            attendance_count = attendance_model.search_count([
                ('employee_id', '=', employee.id),
                ('check_in', '>=', yesterday_start),
                ('check_in', '<=', yesterday_end),
            ])
            
            # Nếu không có bản ghi chấm công và không có nghỉ phép
            if attendance_count == 0:
                # Kiểm tra nghỉ phép
                leave_count = self.env['hr.leave'].search_count([
                    ('employee_id', '=', employee.id),
                    ('date_from', '<=', yesterday_end),
                    ('date_to', '>=', yesterday_start),
                    ('state', '=', 'validate'),
                ])
                
                if leave_count == 0:
                    # Gửi thông báo cho nhân viên
                    employee.user_id.partner_id.message_post(
                        body=f"Bạn không có dữ liệu chấm công vào ngày {yesterday}. Vui lòng kiểm tra lại.",
                        subject="Thông báo thiếu chấm công",
                        message_type='notification',
                        subtype_id=self.env.ref('mail.mt_note').id,
                    )
        
        return True