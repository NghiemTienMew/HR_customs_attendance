odoo.define('vietnam_attendance.qrcode', function (require) {
"use strict";

var AbstractAction = require('web.AbstractAction');
var core = require('web.core');
var session = require('web.session');
var QWeb = core.qweb;
var _t = core._t;

/**
 * Widget để xử lý chức năng chấm công bằng QR code
 */
var AttendanceQRCode = AbstractAction.extend({
    template: 'VietnamAttendanceQRCode',
    events: {
        'click .o_vietnam_attendance_qrcode_scan': '_onScanQRCode',
    },

    /**
     * @override
     */
    init: function (parent, options) {
        this._super.apply(this, arguments);
        this.options = options || {};
        this.attendanceType = this.options.attendanceType || 'check_in';
    },

    /**
     * @override
     */
    start: function () {
        var self = this;
        return this._super.apply(this, arguments).then(function () {
            self._initializeQRScanner();
        });
    },

    /**
     * Khởi tạo scanner QR code
     * @private
     */
    _initializeQRScanner: function () {
        var self = this;
        this.videoElement = this.$('.o_vietnam_attendance_qrcode_video')[0];

        // Kiểm tra hỗ trợ getUserMedia
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } })
                .then(function (stream) {
                    self.videoElement.srcObject = stream;
                    self.videoElement.play();
                    self._startQRScanning();
                })
                .catch(function (error) {
                    self._showError(_t('Không thể truy cập camera: ') + error.message);
                });
        } else {
            this._showError(_t('Trình duyệt của bạn không hỗ trợ camera'));
        }
    },

    /**
     * Bắt đầu quét QR code
     * @private
     */
    _startQRScanning: function () {
        var self = this;
        
        // Sử dụng thư viện jsQR để quét QR code
        this.scanInterval = setInterval(function () {
            if (self.videoElement.readyState === self.videoElement.HAVE_ENOUGH_DATA) {
                var canvas = document.createElement('canvas');
                var context = canvas.getContext('2d');
                var width = self.videoElement.videoWidth;
                var height = self.videoElement.videoHeight;
                
                canvas.width = width;
                canvas.height = height;
                context.drawImage(self.videoElement, 0, 0, width, height);
                
                var imageData = context.getImageData(0, 0, width, height);
                
                // Giả sử jsQR đã được nạp
                if (window.jsQR) {
                    var code = window.jsQR(imageData.data, width, height);
                    
                    if (code) {
                        self._processQRCode(code.data);
                    }
                }
            }
        }, 500);
    },

    /**
     * Dừng quét QR code
     * @private
     */
    _stopQRScanning: function () {
        if (this.scanInterval) {
            clearInterval(this.scanInterval);
            this.scanInterval = null;
        }
        
        if (this.videoElement && this.videoElement.srcObject) {
            this.videoElement.srcObject.getTracks().forEach(function (track) {
                track.stop();
            });
        }
    },

    /**
     * Xử lý dữ liệu QR code
     * @param {String} qrData Dữ liệu QR code
     * @private
     */
    _processQRCode: function (qrData) {
        var self = this;
        this._stopQRScanning();
        
        try {
            var qrDataObj = JSON.parse(qrData);
            
            // Xác thực QR code
            if (!qrDataObj.employee_id || !qrDataObj.barcode) {
                this._showError(_t('Mã QR không hợp lệ'));
                return;
            }
            
            // Gửi yêu cầu chấm công
            var endpoint = (this.attendanceType === 'check_in') ? '/vietnam_attendance/check_in' : '/vietnam_attendance/check_out';
            var params = {
                check_in_method: 'qrcode',
                qrcode_data: qrDataObj,
            };
            
            this._rpc({
                route: endpoint,
                params: params,
            }).then(function (result) {
                if (result.success) {
                    self._showSuccess(result.message);
                    self.do_action({
                        type: 'ir.actions.client',
                        tag: 'vietnam_attendance_dashboard',
                    });
                } else {
                    self._showError(result.message);
                }
            }).catch(function (error) {
                self._showError(_t('Lỗi: ') + error.message);
            });
            
        } catch (error) {
            this._showError(_t('Dữ liệu QR code không hợp lệ'));
        }
    },

    /**
     * Hiển thị thông báo thành công
     * @param {String} message Thông báo
     * @private
     */
    _showSuccess: function (message) {
        this.do_notify(_t('Thành công'), message, true);
    },

    /**
     * Hiển thị thông báo lỗi
     * @param {String} message Thông báo lỗi
     * @private
     */
    _showError: function (message) {
        this.do_warn(_t('Lỗi'), message, true);
    },

    /**
     * Xử lý sự kiện khi nhấn nút quét QR
     * @private
     */
    _onScanQRCode: function () {
        this._initializeQRScanner();
    },

    /**
     * @override
     */
    destroy: function () {
        this._stopQRScanning();
        this._super.apply(this, arguments);
    },
});

core.action_registry.add('vietnam_attendance_qrcode', AttendanceQRCode);

return AttendanceQRCode;

});