import { Injectable } from '@angular/core';

@Injectable({
    providedIn: 'root',
})
export class ToastService {
    toasts: any[] = [];

    show_sccess(text: string, options: any = {}) {
        this.toasts.push({
            icon_color: '#198754',
            autohide: true,
            text,
            ...options,
        });
    }

    show_info(text: string, options: any = {}) {
        this.toasts.push({
            icon_color: '#0dcaf0',
            autohide: true,
            text,
            ...options,
        });
    }

    remove(toast: any) {
        // NOTE: ひとまず，何もしない
    }
}
