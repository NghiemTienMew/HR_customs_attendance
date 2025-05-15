from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import pytz
import logging

_logger = logging.getLogger(__name__)

class VietnamAttendanceShift(models.Model):
    _name = 'vietnam.attendance.shift'
    _description = 'Ca làm việc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'

    name = fields.Char(string='Tên ca làm việc', required=True, tracking=True)
    code = fields.Char(string='Mã ca làm việc', required=True, tracking=True)
    start_time = fields.Float(string='Giờ bắt đầu', required=True, tracking=True)
    end_time = fields.Float(string='Giờ kết thúc', required=True, tracking=True)
    break_start = fields.Float(string='Giờ bắt đầu nghỉ')
    break_end = fields.Float(string='Giờ kết thúc nghỉ')
    
    working_hours = fields.Float(string='Số giờ làm việc', compute='_compute_working_hours', store=True)
    grace_late_minutes = fields.Float(string='Thời gian ân hạn đi muộn (phút)', default=15.0)
    grace_early_leave_minutes = fields.Float(string='Thời gian ân hạn về sớm (phút)', default=15.0)
    
    is_night_shift = fields.Boolean(string='Ca đêm', default=False)
    is_overtime_shift = fields.Boolean(string='Ca tăng ca', default=False)
    
    sequence = fields.Integer(string='Thứ tự', default=10)
    active = fields.Boolean(string='Đang hoạt động', default=True)
    color = fields.Integer(string='Màu sắc')
    
    company_id = fields.Many2one('res.company', string='Công ty', default=lambda self: self.env.company)
    department_ids = fields.Many2many('hr.department', string='Áp dụng cho phòng ban')
    
    weekday_ids = fields.Many2many('vietnam.attendance.weekday', string='Ngày trong tuần')
    flexible = fields.Boolean(string='Ca linh hoạt', default=False, help="Ca làm việc linh hoạt không có giờ cố định")
    
    required_working_hours = fields.Float(string='Số giờ làm việc yêu cầu', help="Số giờ làm việc yêu cầu cho ca linh hoạt")
    
    @api.depends('start_time', 'end_time', 'break_start', 'break_end')
    def _compute_working_hours(self):
        for shift in self:
            working_hours = shift.end_time - shift.start_time
            
            # Trừ thời gian nghỉ nếu có
            if shift.break_start and shift.break_end:
                break_hours = shift.break_end - shift.break_start
                working_hours -= break_hours
            
            # Xử lý trường hợp ca đêm (qua 0h)
            if shift.end_time < shift.start_time:
                working_hours += 24
            
            shift.working_hours = max(0, working_hours)
    
    @api.constrains('start_time', 'end_time')
    def _check_times(self):
        for shift in self:
            if not shift.flexible and shift.start_time == shift.end_time:
                raise ValidationError(_('Giờ bắt đầu và giờ kết thúc không thể giống nhau.'))
            
            if shift.break_start and shift.break_end:
                if shift.break_start >= shift.break_end:
                    raise ValidationError(_('Giờ bắt đầu nghỉ phải nhỏ hơn giờ kết thúc nghỉ.'))
                
                # Đối với ca thông thường (không qua 0h)
                if shift.start_time < shift.end_time:
                    if shift.break_start < shift.start_time or shift.break_end > shift.end_time:
                        raise ValidationError(_('Thời gian nghỉ phải nằm trong khoảng thời gian làm việc.'))
                # Đối với ca đêm (qua 0h)
                else:
                    if (shift.break_start < shift.start_time and shift.break_start > shift.end_time) or \
                       (shift.break_end < shift.start_time and shift.break_end > shift.end_time):
                        raise ValidationError(_('Thời gian nghỉ phải nằm trong khoảng thời gian làm việc.'))
    
    @api.model
    def find_matching_shift(self, employee_id, check_time=None):
        """
        Tìm ca làm việc phù hợp cho nhân viên tại thời điểm chấm công
        """
        employee = self.env['hr.employee'].browse(employee_id)
        if not employee:
            return False
        
        # Nếu không có thời gian kiểm tra, sử dụng thời gian hiện tại
        if not check_time:
            check_time = fields.Datetime.now()
        
        # Chuyển đổi sang múi giờ của người dùng
        tz = pytz.timezone(self.env.user.tz or 'UTC')
        check_time_local = pytz.utc.localize(check_time).astimezone(tz)
        
        # Lấy ngày trong tuần (0 = Thứ 2, ..., 6 = Chủ nhật)
        weekday = check_time_local.weekday()
        if weekday == 6:  # Chuyển đổi Chủ nhật từ 6 sang 0 nếu cần
            weekday = 0
        else:
            weekday += 1  # Chuyển đổi sang 1 = Thứ 2, ..., 7 = Chủ nhật
        
        # Tìm ca làm việc cho phòng ban của nhân viên
        department_shifts = self.search([
            ('department_ids', 'in', employee.department_id.id),
            ('active', '=', True),
        ])
        
        # Tìm ca làm việc chung cho tất cả phòng ban
        general_shifts = self.search([
            ('department_ids', '=', False),
            ('active', '=', True),
        ])
        
        # Kết hợp cả hai danh sách
        all_shifts = department_shifts | general_shifts
        
        # Lọc ca làm việc theo ngày trong tuần
        weekday_shifts = all_shifts.filtered(
            lambda s: not s.weekday_ids or any(w.sequence == weekday for w in s.weekday_ids)
        )
        
        # Lấy thời gian hiện tại dưới dạng số giờ (ví dụ: 14.5 cho 14:30)
        current_time = check_time_local.hour + check_time_local.minute / 60.0
        
        # Tìm ca làm việc phù hợp nhất dựa trên thời gian hiện tại
        matched_shift = False
        min_diff = float('inf')
        
        for shift in weekday_shifts:
            if shift.flexible:
                # Đối với ca linh hoạt, đơn giản là chọn ca linh hoạt nếu được chỉ định cho nhân viên
                matched_shift = shift
                break
            
            # Tính toán khoảng cách giữa thời gian hiện tại và thời gian bắt đầu ca
            if shift.start_time <= shift.end_time:  # Ca thông thường
                if shift.start_time <= current_time <= shift.end_time:
                    # Thời gian hiện tại nằm trong ca làm việc
                    diff = min(current_time - shift.start_time, shift.end_time - current_time)
                    if diff < min_diff:
                        min_diff = diff
                        matched_shift = shift
            else:  # Ca qua đêm
                if current_time >= shift.start_time or current_time <= shift.end_time:
                    # Thời gian hiện tại nằm trong ca làm việc qua đêm
                    if current_time >= shift.start_time:
                        diff = current_time - shift.start_time
                    else:
                        diff = 24 - shift.start_time + current_time
                    if diff < min_diff:
                        min_diff = diff
                        matched_shift = shift
        
        return matched_shift