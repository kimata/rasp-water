import { Component, OnInit, EventEmitter, Input, Output } from '@angular/core';

import * as uuid from 'uuid';

@Component({
    selector: 'app-scheduler-entry',
    templateUrl: './scheduler-entry.component.html',
    styleUrls: ['./scheduler-entry.component.scss']
})

export class SchedulerEntryComponent implements OnInit {
    @Output() onChange = new EventEmitter();
    @Input() state;

    constructor() { }
    
    id = uuid.v4();

    timeOptions = {
        format: 'HH:mm',
    };
    
    ngOnInit() {
    }

    update() {
        this.onChange.emit(this.state);
    }
}
