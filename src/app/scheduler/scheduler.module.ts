import { NgModule } from '@angular/core';
import { BrowserAnimationsModule } from '@angular/platform-browser/animations';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms'

import { SchedulerEntryComponent } from './scheduler-entry/scheduler-entry.component';
import { SchedulerControlComponent } from './scheduler-control/scheduler-control.component';

@NgModule({
    imports:      [ CommonModule, FormsModule, BrowserAnimationsModule ],
    declarations: [ SchedulerEntryComponent, SchedulerControlComponent ],
    exports:      [ SchedulerEntryComponent, SchedulerControlComponent ]
})
export class SchedulerModule { }
