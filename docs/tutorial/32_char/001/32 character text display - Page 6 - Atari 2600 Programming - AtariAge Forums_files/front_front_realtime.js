ips.templates.set(`realtime.whosTyping.wrapper`,`
	<div class='ipsLiveActivity ipsLiveActivity--medium ipsLiveActivity--withPulse ipsLiveActivity--typing ipsFlex-inline'>
		<p class='ipsType_reset'>{{{ typingString }}}</p>
	</div>
`);ips.templates.set(`realtime.whosTyping.name`,`
	<em>{{name}}</em>
`);ips.templates.set(`realtime.whosViewing.wrapper`,`
	<div data-role='whosViewing' data-controller='cloud.front.realtime.userListTooltip' style='display: none' class='ipsLiveActivity ipsLiveActivity--medium ipsLiveActivity--withPulse ipsLiveActivity--viewing ipsFlex-inline ipsFlex-ai:center'>
		{{#photos}}<div class='ipsLiveActivity__photos ipsCaterpillar ipsFlex-flex:00'>{{{photos}}}</div>{{/photos}}
		<p class='ipsType_reset'>{{{ viewingString }}}</p>
	</div>
`);ips.templates.set(`realtime.whosViewing.name`,`
	<em>{{name}}</em> 
`);ips.templates.set(`realtime.whosViewing.photo`,`
	<img src='{{photo}}' class='ipsLiveActivity__photo ipsUserPhoto ipsCaterpillar__item ipsDimension:1' alt="">
`);ips.templates.set(`realtime.whosViewing.summary`,`
	<li><span class='ipsLiveActivity ipsLiveActivity--small' data-controller='cloud.front.realtime.userListTooltip'></span></li>
`);ips.templates.set(`realtime.whosViewing.listItem`,`
	<li>{{ username }}</li>
`)
ips.templates.set(`realtime.whosViewing.list`,`
	<strong>{{ title }}</strong>
	<ul class='ipsList_reset' data-ips-whosviewing-list >
		{{{ users }}}
		{{#anon}}
			<li>+{{anon}}</li>
		{{/anon}}
	</ul>
`);
(function($,_,undefined){"use strict";ips.controller.register("cloud.front.realtime.forumsReplyArea",{initialize:function(){this.on("whosTyping.change",this.handleWhosTyping);this.setup();},setup:function(){this._whosTypingContainer=this.scope.find('[data-role="whosTyping"]');this._whosTypingContainer.hide();},handleWhosTyping:function(e,data){if(!data.users.length){this._whosTypingContainer.slideUp('fast',()=>this._whosTypingContainer.html('').hide());return;}
let typingString;switch(data.users.length){case 1:typingString=ips.getString('whosTypingOne',{first:ips.templates.render('realtime.whosTyping.name',{name:data.users[0].username})});break;case 2:typingString=ips.getString('whosTypingTwo',{first:ips.templates.render('realtime.whosTyping.name',{name:data.users[0].username}),second:ips.templates.render('realtime.whosTyping.name',{name:data.users[1].username})});break;default:typingString=ips.getString('whosTypingMultiple');break;}
const contents=ips.templates.render('realtime.whosTyping.wrapper',{typingString});this._whosTypingContainer.html(contents).slideDown('fast');}});})(jQuery,_);;
;(function($,_,undefined){"use strict";ips.controller.register('cloud.front.realtime.forumsTopicRow',{initialize:function(){this.on(document,'socket.viewing',this.handleSocketActiveOnPage);this.on('activeUserCount',this.handleInitialActiveOnPage);this.setup();},setup:function(){this._id=this.scope.identify().attr('id');this._location=this.scope.attr('data-location');this._statsContainer=this.scope.find('[data-statType="num_views"]');this._viewingContainer=null;this._hasReceivedValue=false;this._activeUsers=[];this._anonUsersCount=0;this._count=0;},handleSocketActiveOnPage:function(e,data){if(data.location!==this._location){return;}
this._hasReceivedValue=true;this._toggleActiveUsers(data);},handleInitialActiveOnPage:function(e,data){if(this._hasReceivedValue){return;}
e.stopPropagation();this._toggleActiveUsers(data);},_toggleActiveUsers:function(data){this._activeUsers=data.activeUsers;this._anonUsersCount=data.anonUsers;this._count=this._activeUsers.length+this._anonUsersCount;if(this._viewingContainer===null){this._createViewingContainer();}
if(this._count>0){this._viewingContainer.find('span').text(ips.pluralize(ips.getString('whosViewingSummary',{count:this._count}),this._count));if(!this._viewingContainer.is(':visible')){this._statsContainer.hide();this._viewingContainer.show();}}else if(!this._viewingContainer.is(':hidden')){this._statsContainer.show();this._viewingContainer.hide();}
this.triggerOn('cloud.front.realtime.userListTooltip','userListTooltip.update',{activeUsers:this._activeUsers,anonUsersCount:this._anonUsersCount,totalCount:this._count});},_createViewingContainer:function(){this._viewingContainer=$(ips.templates.render('realtime.whosViewing.summary')).show();this._statsContainer.after(this._viewingContainer);this._statsContainer.hide();$(document).trigger('contentChange',[this._statsContainer]);}});}(jQuery,_));;
(function($,_,undefined){"use strict";ips.controller.register("cloud.front.realtime.userListTooltip",{_userListTooltipLimit:30,initialize:function(){this.on("userListTooltip.update",this.updateTooltip);this.on("mouseenter",this.showTooltip);this.on("mouseleave",this.hideTooltip);this.setup();},setup:function(){this._id=this.scope.identify().attr("id");this._activeUsers=[];this._anonUsersCount=0;this._totalCount=0;},updateTooltip:function(e,data){e.stopPropagation();this._activeUsers=data.activeUsers||[];this._anonUsersCount=data.anonUsersCount||0;this._totalCount=data.totalCount||0;if(this._tooltip){this._tooltip.html(this._buildTooltipContents());}},showTooltip:function(){if(!this._totalCount){this.hideTooltip();return;}
if(!this._tooltip){this._buildTooltip();}
var tooltipPosition=ips.utils.position.positionElem({trigger:this.scope,target:this._tooltip,center:true,above:true,});$(this._tooltip).css({left:tooltipPosition.left+"px",top:tooltipPosition.top+"px",position:tooltipPosition.fixed?"fixed":"absolute",zIndex:ips.ui.zIndex(),});if(tooltipPosition.location.vertical=="top"){this._tooltip.addClass("ipsTooltip_top");}else{this._tooltip.addClass("ipsTooltip_bottom");}
this._tooltip.show();},hideTooltip:function(){if(this._tooltip){this._tooltip.fadeOut();}},_buildTooltipContents:function(){let users=this._activeUsers.slice(0,this._userListTooltipLimit).map(({username})=>ips.templates.render("realtime.whosViewing.listItem",{username,}));let anon=null;let title=ips.pluralize(ips.getString("whosViewingTitle"),this._totalCount);if(this._anonUsersCount){anon=ips.pluralize(ips.getString("whosViewingOthers"),this._anonUsersCount);}
return ips.templates.render("realtime.whosViewing.list",{users:users.join("\n"),anon,title,});},_buildTooltip:function(){let id="elViewingTooltip_"+this._id;$('[data-ips-whosviewing-list]').each((idx,elem)=>{try{let parent=$(elem.get(0).parentNode);while(parent){if(parent.getAttribute('role')==='tooltip')break;parent=parent.parentNode;}
if(parent)$(parent).remove();}catch(e){Debug.log(e);}});let tooltipHTML=ips.templates.render("core.tooltip",{id});ips.getContainer().append(tooltipHTML);this._tooltip=$('#'+id);this._tooltip.html(this._buildTooltipContents());},});})(jQuery,_);;
(function($,_,undefined){"use strict";ips.controller.register("cloud.front.realtime.viewingProvider",{_outboundTimeout:null,_enabled:false,initialize:function(){this.setup();},setup:function(){if(!ips.utils.sockets.enabled()||!ips.getSetting("page_token")){return;}
if(ips.getSetting("realtime_viewing")&&ips.getSetting("realtime_viewing")===false){return;}
this._getActiveUserCounts();},_getActiveUserCounts:function(){ips.getAjax()(`${ips.getSetting("socketUrl")}/live/viewers`,{method:"get",data:{siteId:ips.getSetting("siteId"),},headers:{Authorization:`Bearer ${ips.getSetting("page_token")}`,},}).done((response)=>{if(!response){return;}
for(let[key,data]of Object.entries(response)){if(!data.activeUsers.length&&!data.anonUsers){continue;}
this.scope.find(`[data-location="${key}"]`).trigger("activeUserCount",{...data});}});},});})(jQuery,_);;
(function($,_,undefined){"use strict";ips.controller.register("cloud.front.realtime.viewingService",{_outboundTimeout:null,_enabled:false,initialize:function(){this.on(document,"socket.connected",this.handleSocketConnection);this.on(document,"socket.disconnected",this.handleSocketDisconnection);this.setup();},setup:function(){if(!ips.utils.sockets.enabled()){return;}
if(ips.getSetting("realtime_viewing")&&ips.getSetting("realtime_viewing")===false){return;}
this._enabled=true;this._outboundTimeout=setInterval(()=>{ips.utils.sockets.send("view:pageView");},5000);},destroy:function(){clearInterval(this._outboundTimeout);},handleSocketConnection:function(){if(!this._enabled){return;}
ips.utils.sockets.send("view:pageView");},handleSocketDisconnection:function(){clearInterval(this._outboundTimeout);},});})(jQuery,_);;
(function($,_,undefined){"use strict";ips.controller.register("cloud.front.realtime.whosTyping",{users:{},initialize:function(){this.on(document,"socket.typing:start",this.handleTypingStart);this.on(document,"socket.typing:end",this.handleTypingEnd);this.on("editor.focused",this.editorFocusBlurEvents);},destroy:function(){this._clearAllUsers();},handleTypingStart:function(e,data){if(data.userId===ips.getSetting("memberID")){return;}
const{userId,username,photo}=data;let shouldTriggerChange=true;if(!_.isUndefined(this.users[userId])){shouldTriggerChange=false;}
this._clearUser(userId);this.users[userId]={timeout:setTimeout(()=>this._userTimeout(userId),5000),username,photo,};if(shouldTriggerChange){this._triggerChangeEvent();}},handleTypingEnd:function(e,data){if(data.userId===ips.getSetting("memberID")){return;}
this._clearUser(data.userId);this._triggerChangeEvent();},_clearUser:function(userId){if(_.isUndefined(this.users[userId])){return;}
clearTimeout(this.users[userId].timeout);delete this.users[userId];},_clearAllUsers:function(){if(!Object.keys(this.users).length){return;}
Object.keys(this.users).forEach((userId)=>{this._clearUser(userId);});},_userTimeout:function(userId){this._clearUser(userId);this._triggerChangeEvent();},_triggerChangeEvent:function(){const users=Object.entries(this.users).map(([userId,userData])=>({userId,...userData}));this.trigger("whosTyping.change",{users});},editorFocusBlurEvents:function(e){if(!ips.utils.sockets.enabled()){return;}
if(ips.getSetting("realtime_typing")&&ips.getSetting("realtime_typing")===false){return;}
if(_.isUndefined(ips.getSetting("isAnonymous"))||ips.getSetting("isAnonymous")){return;}
ips.utils.sockets.send(e.namespace==="focused"?"editor:typing-start":"editor:typing-end");},});})(jQuery,_);;
(function($,_,undefined){"use strict";ips.controller.register("cloud.front.realtime.whosViewing",{initialize:function(){this.on(document,"socket.viewing",this.handleUserActive);this.setup();},setup:function(){this._count=0;this._isInViewport=false;this._location=this.scope.attr('data-location');this._id=this.scope.identify().attr('id');this._observer=new IntersectionObserver(this.handleIntersection.bind(this),{rootMargin:"20px",threshold:0,});this._observer.observe(this.scope.get(0));},destroy:function(){this._observer.unobserve(this.scope.get(0));},handleIntersection:function(entries){entries.forEach((entry)=>{this._isInViewport=entry.isIntersecting;this.maybeToggleUserActive();});},maybeToggleUserActive:function(){if(!this._isInViewport){return;}
const container=this.scope.find('[data-role="whosViewing"]');const additionalClasses=this.scope.attr("data-visibleClass");if(this._count&&!container.is(":visible")){container.addClass(additionalClasses).fadeIn("fast");return;}
if(!this._count&&container.is(":visible")){container.fadeOut("fast",()=>{container.html("").removeClass(additionalClasses).hide();});return;}},handleUserActive:function(e,data){if(this._location!==data.location){return;}
this._activeUsers=data.activeUsers.filter((user)=>user.userId!==ips.getSetting("memberID"));this._anonUsersCount=data.anonUsers;if(_.isUndefined(ips.getSetting("isAnonymous"))||ips.getSetting("isAnonymous")){this._anonUsersCount=Math.max(0,--this._anonUsersCount);}
this._count=this._activeUsers.length+this._anonUsersCount;if(this._count===0){this.maybeToggleUserActive();return;}
const contents=ips.templates.render("realtime.whosViewing.wrapper",{viewingString:this._buildViewingText(this._activeUsers,this._anonUsersCount),photos:this._buildViewingPhotos(this._activeUsers),});this.scope.html(contents);$(document).trigger('contentChange',[this.scope]);this.triggerOn('cloud.front.realtime.userListTooltip','userListTooltip.update',{activeUsers:this._activeUsers,anonUsersCount:this._anonUsersCount,totalCount:this._count});this.maybeToggleUserActive();},_buildViewingText:function(activeUsers,anonUsersCount){const namesToShow=activeUsers.length?activeUsers.slice(0,2).map(user=>user.username):[];const excessNames=activeUsers.slice(2).length+anonUsersCount;const strings=[...namesToShow];if(excessNames){strings.push(ips.pluralize(ips.getString("whosViewingOthers"),excessNames));}
switch(strings.length){case 2:return ips.getString("whosViewingTwo",{first:strings[0],second:strings[1]});break;case 3:return ips.getString("whosViewingThree",{first:strings[0],second:strings[1],third:strings[2]});break;case 1:default:return ips.getString("whosViewingOne",{first:strings[0]});break;}},_buildViewingPhotos:function(users){return users.slice(0,3).map((user)=>ips.templates.render("realtime.whosViewing.photo",{photo:user.photo})).join("");},});})(jQuery,_);;