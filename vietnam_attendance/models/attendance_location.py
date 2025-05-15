from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
from math import radians, cos, sin, asin, sqrt

_logger = logging.getLogger(__name__)

class VietnamAttendanceLocation(models.Model):
    _name = 'vietnam.attendance.location'
    _description = 'Địa điểm chấm công'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Tên địa điểm', required=True, tracking=True)
    address = fields.Text(string='Địa chỉ', tracking=True)
    
    latitude = fields.Float(string='Vĩ độ', digits=(16, 10), tracking=True)
    longitude = fields.Float(string='Kinh độ', digits=(16, 10), tracking=True)
    radius = fields.Float(string='Bán kính (mét)', default=100.0, tracking=True,
                         help='Bán kính cho phép chấm công từ địa điểm này')
    
    wifi_ssid = fields.Char(string='WiFi SSID', tracking=True,
                           help='SSID của mạng WiFi tại địa điểm này')
    wifi_bssid = fields.Char(string='WiFi BSSID', tracking=True,
                            help='BSSID (địa chỉ MAC) của mạng WiFi tại địa điểm này')
    
    active = fields.Boolean(string='Đang hoạt động', default=True)
    company_id = fields.Many2one('res.company', string='Công ty', default=lambda self: self.env.company)
    
    device_ids = fields.One2many('vietnam.attendance.device', 'location_id', string='Thiết bị chấm công')
    department_ids = fields.Many2many('hr.department', string='Phòng ban áp dụng')
    
    allow_check_in = fields.Boolean(string='Cho phép chấm công vào', default=True)
    allow_check_out = fields.Boolean(string='Cho phép chấm công ra', default=True)
    
    image = fields.Binary(string='Hình ảnh địa điểm')
    color = fields.Integer(string='Màu sắc')
    
    @api.constrains('radius')
    def _check_radius(self):
        for location in self:
            if location.radius <= 0:
                raise ValidationError(_('Bán kính phải lớn hơn 0'))
    
    def check_location_in_radius(self, latitude, longitude):
        """
        Kiểm tra xem tọa độ có nằm trong bán kính của địa điểm không
        Sử dụng công thức Haversine để tính khoảng cách giữa hai điểm trên mặt cầu
        """
        self.ensure_one()
        
        if not latitude or not longitude or not self.latitude or not self.longitude:
            return False
        
        # Chuyển đổi tọa độ từ độ sang radian
        lat1, lon1 = radians(latitude), radians(longitude)
        lat2, lon2 = radians(self.latitude), radians(self.longitude)
        
        # Công thức Haversine
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a))
        r = 6371000  # Bán kính trái đất tính bằng mét
        
        # Tính khoảng cách
        distance = c * r
        
        return distance <= self.radius
    
    def check_wifi_match(self, ssid, bssid=None):
        """
        Kiểm tra xem thông tin WiFi có khớp với địa điểm không
        """
        self.ensure_one()
        
        if not ssid or not self.wifi_ssid:
            return False
        
        # Kiểm tra SSID
        if self.wifi_ssid.lower() != ssid.lower():
            return False
        
        # Kiểm tra BSSID nếu có
        if bssid and self.wifi_bssid and self.wifi_bssid.lower() != bssid.lower():
            return False
        
        return True
    
    @api.model
    def find_matching_location(self, latitude=None, longitude=None, ssid=None, bssid=None, employee=None):
        """
        Tìm địa điểm phù hợp dựa trên tọa độ hoặc thông tin WiFi
        """
        domain = [('active', '=', True)]
        
        # Thêm điều kiện công ty nếu có
        if self.env.company:
            domain.append(('company_id', '=', self.env.company.id))
        
        # Thêm điều kiện phòng ban nếu có employee
        if employee and employee.department_id:
            domain.append('|')
            domain.append(('department_ids', '=', False))
            domain.append(('department_ids', 'in', employee.department_id.id))
        
        locations = self.search(domain)
        
        matching_locations = []
        
        # Kiểm tra từng địa điểm
        for location in locations:
            # Kiểm tra tọa độ
            if latitude and longitude and location.check_location_in_radius(latitude, longitude):
                matching_locations.append(location)
                continue
            
            # Kiểm tra WiFi
            if ssid and location.check_wifi_match(ssid, bssid):
                matching_locations.append(location)
                continue
        
        return matching_locations