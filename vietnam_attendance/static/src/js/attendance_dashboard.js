odoo.define('vietnam_attendance.dashboard', function (require) {
"use strict";

var AbstractAction = require('web.AbstractAction');
var core = require('web.core');
var session = require('web.session');
var QWeb = core.qweb;
var _t = core._t;

var AttendanceDashboard = AbstractAction.extend({
    template: 'VietnamAttendanceDashboard',
    events: {
        'click .o_vietnam_attendance_check_in': '_onCheckIn',
        'click .o_vietnam_attendance_check_out': '_onCheckOut',
        'click .o_vietnam_attendance_overtime': '_onOvertimeRequest',
        'click .o_vietnam_attendance_report': '_onAttendanceReport',
    },

    init: function (parent, context) {
        this._super(parent, context);
        this.dashboardData = {};
    },

    willStart: function () {
        var self = this;
        return this._super().then(function () {
            return self._fetchDashboardData();
        });
    },

    start: function () {
        var self = this;
        return this._super().then(function () {
            self._renderDashboard();
        });
    },

    _fetchDashboardData: function () {
        var self = this;
        return this._rpc({
            route: '/vietnam_attendance/get_attendance_status',
        }).then(function (result) {
            self.dashboardData = result;
        });
    },

    _renderDashboard: function () {
        this.$('.o_vietnam_attendance_dashboard').html(QWeb.render('VietnamAttendanceDashboardContent', {
            widget: this
        }));
    },

    _onCheckIn: function () {
        var self = this;

        this._rpc({
            model: 'hr.employee',
            method: 'action_check_in',
            args: [session.uid],
        }).then(function (result) {
            if (result) {
                self.do_action(result);
            }
            self._fetchDashboardData().then(function () {
                self._renderDashboard();
            });
        }).guardedCatch(function (error) {
            self.do_warn(_t('Lỗi'), error.message.data.message);
        });
    },

    _onCheckOut: function () {
        var self = this;

        this._rpc({
            model: 'hr.employee',
            method: 'action_check_out',
            args: [session.uid],
        }).then(function (result) {
            if (result) {
                self.do_action(result);
            }
            self._fetchDashboardData().then(function () {
                self._renderDashboard();
            });
        }).guardedCatch(function (error) {
            self.do_warn(_t('Lỗi'), error.message.data.message);
        });
    },

    _onOvertimeRequest: function () {
        this.do_action({
            name: _t('Tạo yêu cầu tăng ca'),
            type: 'ir.actions.act_window',
            res_model: 'vietnam.attendance.overtime',
            view_mode: 'form',
            views: [[false, 'form']],
            target: 'new',
            context: {
                'default_employee_id': this.dashboardData.employee_id,
            },
        });
    },

    _onAttendanceReport: function () {
        // Lấy ngày đầu tháng và cuối tháng
        var today = new Date();
        var firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
        var lastDay = new Date(today.getFullYear(), today.getMonth() + 1, 0);

        var firstDayStr = firstDay.toISOString().split('T')[0];
        var lastDayStr = lastDay.toISOString().split('T')[0];

        this.do_action({
            name: _t('Báo cáo chấm công'),
            type: 'ir.actions.act_window',
            res_model: 'vietnam.attendance.report',
            view_mode: 'pivot,graph',
            views: [[false, 'pivot'], [false, 'graph']],
            domain: [
                ['employee_id', '=', this.dashboardData.employee_id],
                ['date', '>=', firstDayStr],
                ['date', '<=', lastDayStr],
            ],
            context: {
                'group_by': ['date:day'],
            },
        });
    },
});

core.action_registry.add('vietnam_attendance_dashboard', AttendanceDashboard);

return AttendanceDashboard;

});