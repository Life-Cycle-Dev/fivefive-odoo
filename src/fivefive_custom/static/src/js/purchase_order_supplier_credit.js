/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { FormController } from "@web/views/form/form_controller";

patch(FormController.prototype, {
    setup() {
        super.setup(...arguments);
        this.actionService = useService("action");
        this._skipSupplierCreditWizard = false;
    },

    async beforeExecuteActionButton(clickParams) {
        this._skipSupplierCreditWizard = clickParams.type === "object";
        try {
            return await super.beforeExecuteActionButton(clickParams);
        } finally {
            this._skipSupplierCreditWizard = false;
        }
    },

    async _tryOpenSupplierCreditWizard(record) {
        if (
            this._skipSupplierCreditWizard ||
            record.resModel !== "five.five.purchase.order" ||
            !record.resId
        ) {
            return;
        }
        const action = await this.orm.call(
            "five.five.purchase.order",
            "action_try_open_supplier_credit_wizard",
            [[record.resId]]
        );
        if (action && typeof action === "object") {
            await this.actionService.doAction(action);
        }
    },

    async save(params) {
        const saved = await super.save(params);
        if (saved) {
            await this._tryOpenSupplierCreditWizard(this.model.root);
        }
        return saved;
    },
});
