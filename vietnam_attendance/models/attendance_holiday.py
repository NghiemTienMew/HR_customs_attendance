from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class VietnamAttendanceHoliday(models.Model):
    _name = 'vietnam.attendance.holiday'
    _description = 'Ngày nghỉ lễ'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date'

    name = fields.Char(string='Tên ngày lễ', required=True, tracking=True)
    date = fields.Date(string='Ngày', required=True, tracking=True)
    
    type = fields.Selection([
        ('public', 'Nghỉ lễ chính thức'),
        ('company', 'Nghỉ lễ công ty'),
        ('other', 'Khác'),
    ], string='Loại ngày lễ', required=True, default='public', tracking=True)
    
    description = fields.Text(string='Mô tả')
    active = fields.Boolean(string='Đang hoạt động', default=True)
    
    company_id = fields.Many2one('res.company', string='Công ty', default=lambda self: self.env.company)
    country_id = fields.Many2one('res.country', string='Quốc gia', default=lambda self: self.env.company.country_id)
    
    is_paid = fields.Boolean(string='Được thanh toán', default=True,
                           help='Nhân viên được trả lương cho ngày nghỉ lễ này')
    
    department_ids = fields.Many2many('hr.department', string='Phòng ban áp dụng',
                                    help='Để trống nếu áp dụng cho tất cả phòng ban')
    
    # Tính năng lặp lại hàng năm
    repeat_annually = fields.Boolean(string='Lặp lại hàng năm', default=False)
    
    # Tính toán ngày trong tuần
    day_of_week = fields.Selection([
        ('1', 'Thứ 2'),
        ('2', 'Thứ 3'),
        ('3', 'Thứ 4'),
        ('4', 'Thứ 5'),
        ('5', 'Thứ 6'),
        ('6', 'Thứ 7'),
        ('7', 'Chủ nhật'),
    ], string='Ngày trong tuần', compute='_compute_day_of_week', store=True)
    
    # Các ngày bù (nếu ngày lễ trùng với cuối tuần)
    compensate_date = fields.Date(string='Ngày nghỉ bù')
    
    @api.depends('date')
    def _compute_day_of_week(self):
        for holiday in self:
            if holiday.date:
                # Chuyển đổi từ 0-6 (Mon-Sun) sang 1-7 (Mon-Sun)
                weekday = holiday.date.weekday() + 1
                holiday.day_of_week = str(weekday)
            else:
                holiday.day_of_week = False
    
    @api.constrains('date', 'company_id')
    def _check_duplicate_date(self):
        for holiday in self:
            domain = [
                ('date', '=', holiday.date),
                ('company_id', '=', holiday.company_id.id),
                ('id', '!=', holiday.id),
            ]
            if self.search_count(domain) > 0:
                raise ValidationError(_('Đã tồn tại ngày nghỉ lễ cho ngày này'))
    
    @api.model
    def create_public_holidays_for_vietnam(self, year=None):
        """
        Tạo các ngày nghỉ lễ chính thức của Việt Nam cho năm được chỉ định
        """
        if not year:
            year = fields.Date.today().year
        
        # Tìm quốc gia Việt Nam
        vietnam = self.env['res.country'].search([('code', '=', 'VN')], limit=1)
        if not vietnam:
            raise UserError(_('Không tìm thấy quốc gia Việt Nam trong hệ thống'))
        
        # Danh sách các ngày lễ chính thức của Việt Nam
        vietnam_holidays = [
            # Tết dương lịch
            {'name': 'Tết Dương lịch', 'day': 1, 'month': 1, 'days': 1},
            # Tết Nguyên đán (cần tính toán theo lịch âm, tạm thời dùng ngày cố định)
            {'name': 'Tết Nguyên đán', 'day': 1, 'month': 2, 'days': 5},
            # Giỗ tổ Hùng Vương (cần tính toán theo lịch âm, tạm thời dùng ngày cố định)
            {'name': 'Giỗ tổ Hùng Vương', 'day': 10, 'month': 4, 'days': 1},
            # Ngày thống nhất đất nước
            {'name': 'Ngày Thống nhất đất nước', 'day': 30, 'month': 4, 'days': 1},
            # Ngày Quốc tế Lao động
            {'name': 'Ngày Quốc tế Lao động', 'day': 1, 'month': 5, 'days': 1},
            # Quốc khánh
            {'name': 'Quốc khánh', 'day': 2, 'month': 9, 'days': 2},
        ]
        
        # Tạo các ngày nghỉ lễ
        for holiday_info in vietnam_holidays:
            for day_offset in range(holiday_info['days']):
                holiday_date = fields.Date.from_string(f"{year}-{holiday_info['month']:02d}-{holiday_info['day']:02d}") + timedelta(days=day_offset)
                
                # Kiểm tra xem ngày lễ đã tồn tại chưa
                existing_holiday = self.search([
                    ('date', '=', holiday_date),
                    ('company_id', '=', self.env.company.id),
                    ('type', '=', 'public'),
                ])
                
                if not existing_holiday:
                    self.create({
                        'name': f"{holiday_info['name']}{' (ngày ' + str(day_offset + 1) + ')' if day_offset > 0 else ''}",
                        'date': holiday_date,
                        'type': 'public',
                        'country_id': vietnam.id,
                        'is_paid': True,
                        'repeat_annually': True,
                        'description': f"Ngày nghỉ lễ chính thức của Việt Nam: {holiday_info['name']}",
                    })
        
        return True
    
    @api.model
    def check_is_holiday(self, date, employee=None):
        """
        Kiểm tra xem một ngày có phải là ngày nghỉ lễ không
        """
        if isinstance(date, str):
            date = fields.Date.from_string(date)
        
        domain = [
            ('date', '=', date),
            ('active', '=', True),
            '|', ('company_id', '=', self.env.company.id), ('company_id', '=', False),
        ]
        
        # Nếu có thông tin nhân viên, kiểm tra phòng ban
        if employee and employee.department_id:
            domain.extend([
                '|',
                ('department_ids', '=', False),
                ('department_ids', 'in', employee.department_id.id),
            ])
        
        holidays = self.search(domain)
        
        return bool(holidays)
    
    def generate_holidays_for_next_year(self):
        """
        Tạo các ngày nghỉ lễ lặp lại hàng năm cho năm tiếp theo
        """
        next_year = fields.Date.today().year + 1
        
        # Tìm các ngày lễ lặp lại hàng năm
        annual_holidays = self.search([
            ('repeat_annually', '=', True),
            ('active', '=', True),
        ])
        
        for holiday in annual_holidays:
            next_date = fields.Date.from_string(
                f"{next_year}-{holiday.date.month:02d}-{holiday.date.day:02d}"
            )
            
            # Kiểm tra xem ngày lễ đã tồn tại cho năm tiếp theo chưa
            existing_holiday = self.search([
                ('date', '=', next_date),
                ('company_id', '=', holiday.company_id.id),
                ('name', '=', holiday.name),
            ])
            
            if not existing_holiday:
                # Tạo ngày lễ mới cho năm tiếp theo
                holiday.copy({
                    'date': next_date,
                })
        
        return True