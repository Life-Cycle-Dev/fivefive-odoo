/** @odoo-module **/

import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { patch } from "@web/core/utils/patch";
import { useChildRef, useService } from "@web/core/utils/hooks";
import { ListRenderer } from "@web/views/list/list_renderer";
import { Component, useState, xml } from "@odoo/owl";

const CONFIRM_DELETE_CLASS = "ff_confirm_list_delete";

const DEFAULT_CONFIRM_PHRASE = "confirm delete";

class ConfirmDeleteTypedDialog extends Component {
    static components = { Dialog };
    static props = {
        close: Function,
        title: {
            validate: (m) => {
                return (
                    typeof m === "string" ||
                    (typeof m === "object" && typeof m.toString === "function")
                );
            },
            optional: true,
        },
        body: { type: String, optional: true },
        confirmPhrase: { type: String, optional: true },
        confirm: { type: Function, optional: true },
        confirmLabel: { type: String, optional: true },
        confirmClass: { type: String, optional: true },
        cancel: { type: Function, optional: true },
        cancelLabel: { type: String, optional: true },
        dismiss: { type: Function, optional: true },
    };
    static defaultProps = {
        confirmPhrase: DEFAULT_CONFIRM_PHRASE,
        confirmLabel: _t("ตกลง"),
        cancelLabel: _t("ยกเลิก"),
        confirmClass: "btn-danger",
        title: _t("ยืนยันการลบ"),
    };

    static template = xml`
        <Dialog size="'md'" title="props.title" modalRef="modalRef">
            <p t-out="props.body" class="text-prewrap mb-3"/>
            <label class="form-label">
                <t t-esc="labelBeforePhrase"/>
                <strong style="font-weight: 700" t-esc="confirmPhrasePlain"/>
                <t t-esc="labelAfterPhrase"/>
            </label>
            <input
                type="text"
                class="form-control"
                autocomplete="off"
                t-att-placeholder="props.confirmPhrase"
                t-att-value="state.input"
                t-on-input="onInput"
            />
            <t t-set-slot="footer">
                <button
                    class="btn"
                    t-att-class="props.confirmClass"
                    t-att-disabled="!phraseMatches"
                    t-on-click="_confirm"
                    t-esc="props.confirmLabel"
                />
                <button
                    t-if="props.cancel"
                    class="btn btn-secondary"
                    t-on-click="_cancel"
                    t-esc="props.cancelLabel"
                />
            </t>
        </Dialog>
    `;

    setup() {
        this.env.dialogData.dismiss = () => this._dismiss();
        this.modalRef = useChildRef();
        this.isProcess = false;
        this.state = useState({ input: "" });
    }

    get expectedPhrase() {
        return (this.props.confirmPhrase || DEFAULT_CONFIRM_PHRASE).trim().toLowerCase();
    }

    get phraseMatches() {
        return this.state.input.trim().toLowerCase() === this.expectedPhrase;
    }

    get labelBeforePhrase() {
        return _t("พิมพ์ ");
    }

    get confirmPhrasePlain() {
        return this.props.confirmPhrase || DEFAULT_CONFIRM_PHRASE;
    }

    get labelAfterPhrase() {
        return _t(" ในช่องด้านล่างเพื่อยืนยัน");
    }

    onInput(ev) {
        this.state.input = ev.target.value;
    }

    async _cancel() {
        return this.execButton(this.props.cancel);
    }

    async _confirm() {
        if (!this.phraseMatches) {
            return;
        }
        return this.execButton(this.props.confirm);
    }

    async _dismiss() {
        return this.execButton(this.props.dismiss || this.props.cancel);
    }

    setButtonsDisabled(disabled) {
        this.isProcess = disabled;
        if (!this.modalRef.el) {
            return;
        }
        for (const button of [...this.modalRef.el.querySelectorAll(".modal-footer button")]) {
            button.disabled = disabled;
        }
    }

    async execButton(callback) {
        if (this.isProcess) {
            return;
        }
        this.setButtonsDisabled(true);
        if (callback) {
            let shouldClose;
            try {
                shouldClose = await callback();
            } catch (e) {
                this.props.close();
                throw e;
            }
            if (shouldClose === false) {
                this.setButtonsDisabled(false);
                return;
            }
        }
        this.props.close();
    }
}

function listArchRequestsDeleteConfirm(archInfo) {
    const cls = archInfo?.className;
    if (!cls || typeof cls !== "string") {
        return false;
    }
    return cls.trim().split(/\s+/).includes(CONFIRM_DELETE_CLASS);
}

patch(ListRenderer.prototype, {
    setup() {
        super.setup(...arguments);
        this.dialog = useService("dialog");
    },
    async onDeleteRecord(record, ev) {
        if (!listArchRequestsDeleteConfirm(this.props.archInfo)) {
            return super.onDeleteRecord(...arguments);
        }
        this.keepColumnWidths = true;
        if (this.editedRecord && this.editedRecord !== record) {
            const left = await this.props.list.leaveEditMode();
            if (!left) {
                return;
            }
        }
        if (!this.activeActions.onDelete) {
            return;
        }
        this.dialog.add(ConfirmDeleteTypedDialog, {
            title: _t("ยืนยันการลบ"),
            body: _t(
                "ต้องการลบรายการนี้จริงหรือไม่? ข้อมูลจะถูกลบออกจากระบบและไม่สามารถกู้คืนได้อีก"
            ),
            confirmPhrase: DEFAULT_CONFIRM_PHRASE,
            confirm: () => {
                this.activeActions.onDelete(record);
                return true;
            },
            cancel: () => {},
        });
    },
});
