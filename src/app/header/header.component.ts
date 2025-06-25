import { Component, OnInit } from '@angular/core';
import { NgStyle } from '@angular/common';

@Component({
    selector: 'app-header',
    templateUrl: './header.component.html',
    styleUrls: ['./header.component.scss'],
    imports: [NgStyle],
})
export class HeaderComponent implements OnInit {
    constructor() {}

    ngOnInit() {}
}
