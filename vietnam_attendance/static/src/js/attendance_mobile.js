odoo.define('vietnam_attendance.mobile', function (require) {
"use strict";

var core = require('web.core');
var session = require('web.session');
var mobile = require('web_mobile.core');
var _t = core._t;

/**
 * Chấm công từ ứng dụng di động
 */
var AttendanceMobile = {
    /**
     * Kiểm tra xem thiết bị có hỗ trợ định vị GPS không
     * @returns {Promise} Promise với kết quả kiểm tra
     */
    checkGPSSupport: function () {
        return new Promise(function (resolve, reject) {
            if (navigator.geolocation) {
                resolve(true);
            } else {
                resolve(false);
            }
        });
    },

    /**
     * Lấy tọa độ GPS hiện tại
     * @returns {Promise} Promise với tọa độ GPS
     */
    getCurrentPosition: function () {
        return new Promise(function (resolve, reject) {
            navigator.geolocation.getCurrentPosition(
                function (position) {
                    resolve({
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude,
                        accuracy: position.coords.accuracy,
                    });
                },
                function (error) {
                    reject(error);
                },
                {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 0,
                }
            );
        });
    },

    /**
     * Lấy thông tin WiFi hiện tại (cần hỗ trợ từ ứng dụng mobile)
     * @returns {Promise} Promise với thông tin WiFi
     */
    getWifiInformation: function () {
        return new Promise(function (resolve, reject) {
            if (mobile && mobile.methods && mobile.methods.getWifiInfo) {
                mobile.methods.getWifiInfo({})
                    .then(function (result) {
                        resolve(result);
                    })
                    .catch(function (error) {
                        reject(error);
                    });
            } else {
                reject(new Error(_t('Thiết bị của bạn không hỗ trợ lấy thông tin WiFi')));
            }
        });
    },

    /**
     * Chụp ảnh từ camera (cần hỗ trợ từ ứng dụng mobile)
     * @returns {Promise} Promise với dữ liệu ảnh dạng base64
     */
    takePhoto: function () {
        return new Promise(function (resolve, reject) {
            if (mobile && mobile.methods && mobile.methods.takePhoto) {
                mobile.methods.takePhoto({})
                    .then(function (result) {
                        if (result && result.data) {
                            resolve(result.data);
                        } else {
                            reject(new Error(_t('Không nhận được dữ liệu ảnh')));
                        }
                    })
                    .catch(function (error) {
                        reject(error);
                    });
            } else {
                reject(new Error(_t('Thiết bị của bạn không hỗ trợ chụp ảnh')));
            }
        });
    },

    /**
     * Gửi yêu cầu chấm công vào
     * @param {Object} data Dữ liệu chấm công vào
     * @returns {Promise} Promise với kết quả chấm công
     */
    checkIn: function (data) {
        return new Promise(function (resolve, reject) {
            // Thu thập thông tin chấm công
            var checkInData = {
                check_in_method: data.method || 'manual',
            };

            // Thêm dữ liệu GPS nếu có
            if (data.position) {
                checkInData.latitude = data.position.latitude;
                checkInData.longitude = data.position.longitude;
            }

            // Thêm dữ liệu WiFi nếu có
            if (data.wifi) {
                checkInData.wifi_ssid = data.wifi.ssid;
                checkInData.wifi_bssid = data.wifi.bssid;
            }

            // Thêm dữ liệu ảnh nếu có
            if (data.image) {
                checkInData.image = data.image;
            }

            // Thêm dữ liệu vị trí nếu có
            if (data.location_id) {
                checkInData.location_id = data.location_id;
            }

            // Thêm dữ liệu thiết bị nếu có
            if (data.device_id) {
                checkInData.device_id = data.device_id;
            }

            // Gửi yêu cầu chấm công vào
            session.rpc('/vietnam_attendance/check_in', checkInData)
                .then(function (result) {
                    if (result.success) {
                        resolve(result);
                    } else {
                        reject(new Error(result.message));
                    }
                })
                .catch(function (error) {
                    reject(error);
                });
        });
    },

    /**
     * Gửi yêu cầu chấm công ra
     * @param {Object} data Dữ liệu chấm công ra
     * @returns {Promise} Promise với kết quả chấm công
     */
    checkOut: function (data) {
        return new Promise(function (resolve, reject) {
            // Thu thập thông tin chấm công
            var checkOutData = {
                check_out_method: data.method || 'manual',
                attendance_id: data.attendance_id,
            };

            // Thêm dữ liệu GPS nếu có
            if (data.position) {
                checkOutData.latitude = data.position.latitude;
                checkOutData.longitude = data.position.longitude;
            }

            // Thêm dữ liệu WiFi nếu có
            if (data.wifi) {
                checkOutData.wifi_ssid = data.wifi.ssid;
                checkOutData.wifi_bssid = data.wifi.bssid;
            }

            // Thêm dữ liệu ảnh nếu có
            if (data.image) {
                checkOutData.image = data.image;
            }

            // Thêm dữ liệu vị trí nếu có
            if (data.location_id) {
                checkOutData.location_id = data.location_id;
            }

            // Thêm dữ liệu thiết bị nếu có
            if (data.device_id) {
                checkOutData.device_id = data.device_id;
            }

            // Gửi yêu cầu chấm công ra
            session.rpc('/vietnam_attendance/check_out', checkOutData)
                .then(function (result) {
                    if (result.success) {
                        resolve(result);
                    } else {
                        reject(new Error(result.message));
                    }
                })
                .catch(function (error) {
                    reject(error);
                });
        });
    },

    /**
     * Lấy trạng thái chấm công hiện tại
     * @returns {Promise} Promise với trạng thái chấm công
     */
    getAttendanceStatus: function () {
        return new Promise(function (resolve, reject) {
            session.rpc('/vietnam_attendance/get_attendance_status', {})
                .then(function (result) {
                    if (result.success) {
                        resolve(result);
                    } else {
                        reject(new Error(result.message));
                    }
                })
                .catch(function (error) {
                    reject(error);
                });
        });
    },

    /**
     * Lấy danh sách địa điểm chấm công
     * @returns {Promise} Promise với danh sách địa điểm
     */
    getLocations: function () {
        return new Promise(function (resolve, reject) {
            session.rpc('/vietnam_attendance/get_locations', {})
                .then(function (result) {
                    if (result.success) {
                        resolve(result.locations);
                    } else {
                        reject(new Error(result.message));
                    }
                })
                .catch(function (error) {
                    reject(error);
                });
        });
    },

    /**
     * Xử lý đầy đủ luồng chấm công
     * @param {String} type Loại chấm công ('check_in' hoặc 'check_out')
     * @param {Object} options Tùy chọn bổ sung
     * @returns {Promise} Promise với kết quả chấm công
     */
    processAttendance: function (type, options) {
        var self = this;
        var data = {
            method: options.method || 'gps',
        };

        if (options.attendance_id) {
            data.attendance_id = options.attendance_id;
        }

        if (options.location_id) {
            data.location_id = options.location_id;
        }

        if (options.device_id) {
            data.device_id = options.device_id;
        }

        // Chuỗi xử lý Promise
        return Promise.all([
            // Lấy vị trí GPS nếu cần
            (data.method === 'gps') ? self.getCurrentPosition() : Promise.resolve(null),
            // Lấy thông tin WiFi nếu cần
            (data.method === 'wifi') ? self.getWifiInformation() : Promise.resolve(null),
            // Chụp ảnh nếu cần
            (options.take_photo) ? self.takePhoto() : Promise.resolve(null),
        ])
        .then(function (results) {
            var position = results[0];
            var wifi = results[1];
            var image = results[2];

            if (position) {
                data.position = position;
            }

            if (wifi) {
                data.wifi = wifi;
            }

            if (image) {
                data.image = image;
            }

            // Gửi yêu cầu chấm công
            if (type === 'check_in') {
                return self.checkIn(data);
            } else if (type === 'check_out') {
                return self.checkOut(data);
            } else {
                return Promise.reject(new Error(_t('Loại chấm công không hợp lệ')));
            }
        });
    }
};

return AttendanceMobile;

});