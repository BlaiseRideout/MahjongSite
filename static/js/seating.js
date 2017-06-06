(function($) {
	$(function () {
		var selector = document.getElementById("person");
		var people = document.getElementById("people");
		var tables = document.getElementById("tables");

		$("#addperson").click(function() {
			var val = $(selector).val();
			$.post("/seating/addcurrentplayer", {player:val}, function(data) {
				if(data.status !== 0)
					console.log(data);
				else {
					getCurrentPlayers();
					regenTables();
					window.populatePlayerComplete(true);
					$(selector).val("");
				}
			}, 'json');
		});
		$("#clearplayers").click(function () {
			var clearplayers = $("#clearplayers");
			if(confirm("Really clear current players?")) {
				$.post('/seating/clearcurrentplayers', function(data) {
					if(data.status !== 0)
						console.log(data);
					else {
						refresh();
					}
				}, 'json').fail(xhrError);
			}
		});
		$("#regentables").click(regenTables);

		function removePlayer(player) {
			$.post("/seating/removeplayer", {player:player}, function(data) {
				getCurrentPlayers();
				regenTables();
			}, 'json');
		}

		function prioritizePlayer(player, priority) {
			$.post("/seating/prioritizeplayer", {player:player, priority:priority?1:0}, function(data) {
				getCurrentPlayers();
				regenTables();
			}, 'json');
		}

		function regenTables() {
			$.post("/seating/regentables", function(data) {
				getCurrentTables();
			}, 'json').fail(xhrError);
		}

		function getCurrentPlayers() {
			$.getJSON('/seating/currentplayers.json', function(data) {
				$(people).html("");
				data.forEach(function(playerdata) {
					player = playerdata[0];
					var newplayer = document.createElement("div");
					newplayer.className = "player";

					var priority = document.createElement("input");
					priority.id = player.replace(/ /g, "-") + "-priority";
					priority.type = "checkbox";
					priority.checked = !!playerdata[1];
					priority.className = "priority";
					$(priority).change(function(player) { return function() {
						prioritizePlayer(player, this.checked);
					};}(player));
					newplayer.appendChild(priority);

					var priorityview = document.createElement("label");
					priorityview.htmlFor = priority.id;
					newplayer.appendChild(priorityview);

					var playername = document.createElement("span");
					$(playername).text(player);
					newplayer.appendChild(playername);

					var deleteButton = document.createElement("a");
					$(deleteButton).text("✖");
					deleteButton.className = "deletebutton noselect clickable"
					$(deleteButton).click(function(player) { return function() {
						removePlayer(player);
					};}(player));
					newplayer.appendChild(deleteButton);

					people.appendChild(newplayer);
				});
			}).fail(xhrError);
		}

		function getCurrentTables() {
			$.getJSON('/seating/currenttables.json', function(data) {
				var numplayers = data.length
				var total_tables = 0;
				var tables_5p = 0;
				var tables_4p = 0;
				if(numplayers < 4 || numplayers === 11 || numplayers === 7 || numplayers === 6 || numplayers === 0) {
					$(tables).html("<h1>Invalid number of players: " + numplayers + "</h1>");
					return;
				}
				else if(numplayers >= 8) {
					tables_5p = numplayers % 4;
					total_tables = Math.floor(numplayers / 4);
					tables_4p = total_tables - tables_5p;
				}
				else {
					if(numplayers === 5)
						tables_5p = 1;
					else
						tables_5p = 0;
					total_tables = 1;
					tables_4p = total_tables - tables_5p;
				}

				$(tables).html("");
				var total_players = tables_4p * 4 + tables_5p * 5;
				var table_id = 1;
				for(var i = 0; i < total_players;) {
					var table = document.createElement("div");
					table.className = "table";
					var title = document.createElement("h3");
					$(title).text("TABLE " + table_id++);
					table.appendChild(title);
					var endtable = i + 4;

					if(i >= tables_4p * 4)
						endtable = i + 5;

					var place = 0;
					var places = "東南西北５";
					for(; i < endtable; ++i) {
						var player = document.createElement("div");
						$(player).html("<span class=\"windicator\">" + places[place++] + "</span> " + data[i]);
						table.appendChild(player);
					}
					tables.appendChild(table);
				}
			}).fail(xhrError);
		}

		function refresh() {
			getCurrentPlayers();
			getCurrentTables();
		}
		window.setInterval(function() {
			refresh();
		}, 5000);
		window.populatePlayerComplete();
		refresh();

		function xhrError(xhr, status, error) {
			console.log(status + ": " + error);
			console.log(xhr);
		}
	});
})(jQuery);
