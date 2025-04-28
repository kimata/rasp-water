import { Component, OnInit } from '@angular/core';
import { ToastService } from '../service/toast.service';
import { NgbToast, NgbToastHeader } from '@ng-bootstrap/ng-bootstrap';
import { NgFor } from '@angular/common';

@Component({
    selector: 'app-toast',
    templateUrl: './toast.component.html',
    styleUrls: ['./toast.component.scss'],
    imports: [NgFor, NgbToast, NgbToastHeader]
})
export class ToastComponent implements OnInit {
    constructor(public toastService: ToastService) {}

    ngOnInit() {}
}
