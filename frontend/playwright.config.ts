import {defineConfig} from '@playwright/test';
export default defineConfig({testDir:'./tests',workers:1,
  webServer:{command:'npm exec vite -- --host 127.0.0.1 --port 5175',url:'http://127.0.0.1:5175/longcaster-timeline/',reuseExistingServer:true},
  use:{baseURL:'http://127.0.0.1:5175/longcaster-timeline/',viewport:{width:1920,height:1080}},reporter:'list'});
