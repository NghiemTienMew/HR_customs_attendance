from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
from datetime import datetime, timedelta

_logger = logging.getLogger(__name__)

class VietnamAttendanceRule(models.Model):
    _name = 'vietnam.attendance.rule'
    _description = 'Quy định chấm công'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'

    name = fields.Char(string='Tên quy định', required=True, tracking=True)
    code = fields.Char(string='Mã quy định', required=True, tracking=True)
    
    active = fields.Boolean(string='Đang hoạt động', default=True)
    sequence = fields.Integer(string='Thứ tự', default=10)
    
    rule_type = fields.Selection([
        ('late', 'Đi muộn'),
        ('early_leave', 'Về sớm'),
        ('absence', 'Vắng mặt'),
        ('overtime', 'Tăng ca'),
        ('holiday', 'Ngày lễ'),
        ('weekend', 'Cuối tuần'),
        ('night_shift', 'Ca đêm'),
        ('other', 'Khác'),
    ], string='Loại quy định', required=True, default='late', tracking=True)
    
    time_limit = fields.Float(string='Thời gian giới hạn', 
                             help='Thời gian giới hạn (phút) cho phép đi muộn hoặc về sớm')
    
    deduction_type = fields.Selection([
        ('fixed', 'Cố định'),
        ('percentage', 'Phần trăm'),
        ('formula', 'Công thức'),
    ], string='Loại khấu trừ', default='fixed')
    
    deduction_value = fields.Float(string='Giá trị khấu trừ')
    deduction_formula = fields.Text(string='Công thức khấu trừ',
                                   help='Sử dụng biến: time_late, time_early_leave, absence_days, overtime_hours')
    
    bonus_type = fields.Selection([
        ('fixed', 'Cố định'),
        ('percentage', 'Phần trăm'),
        ('formula', 'Công thức'),
    ], string='Loại thưởng', default='fixed')
    
    bonus_value = fields.Float(string='Giá trị thưởng')
    bonus_formula = fields.Text(string='Công thức thưởng',
                               help='Sử dụng biến: overtime_hours, holiday_hours, weekend_hours, night_shift_hours')
    
    applicable_to_ids = fields.Many2many('hr.employee.category', string='Áp dụng cho')
    department_ids = fields.Many2many('hr.department', string='Phòng ban áp dụng')
    
    company_id = fields.Many2one('res.company', string='Công ty', default=lambda self: self.env.company)
    
    description = fields.Text(string='Mô tả')
    
    @api.constrains('code', 'company_id')
    def _check_unique_code(self):
        for rule in self:
            if rule.code:
                domain = [
                    ('code', '=', rule.code),
                    ('company_id', '=', rule.company_id.id),
                    ('id', '!=', rule.id),
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(_('Mã quy định phải là duy nhất'))
    
    def calculate_deduction(self, time_late=0, time_early_leave=0, absence_days=0, overtime_hours=0):
        """
        Tính toán khấu trừ dựa trên quy định
        """
        self.ensure_one()
        
        if self.deduction_type == 'fixed':
            return self.deduction_value
        
        elif self.deduction_type == 'percentage':
            # Phần trăm được tính trên mức lương cơ bản
            # Cần thêm logic để lấy mức lương cơ bản
            base_salary = 1000000  # Giả định
            return base_salary * self.deduction_value / 100
        
        elif self.deduction_type == 'formula':
            if not self.deduction_formula:
                return 0
            
            try:
                # Tạo biến môi trường để tính toán
                env = {
                    'time_late': time_late,
                    'time_early_leave': time_early_leave,
                    'absence_days': absence_days,
                    'overtime_hours': overtime_hours,
                }
                
                # Thêm các hàm toán học
                import math
                for func_name in dir(math):
                    if not func_name.startswith('_'):
                        env[func_name] = getattr(math, func_name)
                
                # Tính toán công thức
                result = eval(self.deduction_formula, {"__builtins__": {}}, env)
                return float(result)
            except Exception as e:
                _logger.error(f"Lỗi tính toán công thức khấu trừ: {e}")
                return 0
        
        return 0
    
    def calculate_bonus(self, overtime_hours=0, holiday_hours=0, weekend_hours=0, night_shift_hours=0):
        """
        Tính toán thưởng dựa trên quy định
        """
        self.ensure_one()
        
        if self.bonus_type == 'fixed':
            return self.bonus_value
        
        elif self.bonus_type == 'percentage':
            # Phần trăm được tính trên mức lương cơ bản
            # Cần thêm logic để lấy mức lương cơ bản
            base_salary = 1000000  # Giả định
            return base_salary * self.bonus_value / 100
        
        elif self.bonus_type == 'formula':
            if not self.bonus_formula:
                return 0
            
            try:
                # Tạo biến môi trường để tính toán
                env = {
                    'overtime_hours': overtime_hours,
                    'holiday_hours': holiday_hours,
                    'weekend_hours': weekend_hours,
                    'night_shift_hours': night_shift_hours,
                }
                
                # Thêm các hàm toán học
                import math
                for func_name in dir(math):
                    if not func_name.startswith('_'):
                        env[func_name] = getattr(math, func_name)
                
                # Tính toán công thức
                result = eval(self.bonus_formula, {"__builtins__": {}}, env)
                return float(result)
            except Exception as e:
                _logger.error(f"Lỗi tính toán công thức thưởng: {e}")
                return 0
        
        return 0
    
    @api.model
    def get_applicable_rules(self, employee, rule_types=None):
        """
        Lấy danh sách quy định áp dụng cho nhân viên
        """
        domain = [('active', '=', True)]
        
        # Thêm điều kiện loại quy định
        if rule_types:
            if isinstance(rule_types, str):
                rule_types = [rule_types]
            domain.append(('rule_type', 'in', rule_types))
        
        # Thêm điều kiện công ty
        if employee.company_id:
            domain.append(('company_id', '=', employee.company_id.id))
        
        # Lấy tất cả quy định thỏa mãn
        rules = self.search(domain)
        
        # Lọc quy định dựa trên phòng ban và phân loại nhân viên
        applicable_rules = self.env['vietnam.attendance.rule']
        
        for rule in rules:
            # Kiểm tra phòng ban
            if rule.department_ids and employee.department_id not in rule.department_ids:
                continue
            
            # Kiểm tra phân loại nhân viên
            if rule.applicable_to_ids and not any(category in rule.applicable_to_ids for category in employee.category_ids):
                continue
            
            applicable_rules += rule
        
        return applicable_rules