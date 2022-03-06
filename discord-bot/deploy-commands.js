/*
    Acoustats
    Copyright (C) 2022, H. Kamran

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program. If not, see <https://www.gnu.org/licenses/>.
*/

require("dotenv").config();

const { SlashCommandBuilder } = require("@discordjs/builders");
const { REST } = require("@discordjs/rest");
const { Routes } = require("discord-api-types/v9");

const token = process.env.DISCORD_TOKEN;
const clientId = process.env.CLIENT_ID;
// const guildId = process.env.GUILD_ID;

const timeframeOptions = [
    // { label: "Today", value: "today" },
    { label: "This week", value: "this_week" },
    { label: "This month", value: "this_month" },
    { label: "This year", value: "this_year" },
    { label: "Yesterday", value: "yesterday" },
    {
        label: "Last week",
        value: "last_week",
    },
    { label: "Last month", value: "last_month" },
    { label: "Last year", value: "last_year" },
];

const commands = [
    new SlashCommandBuilder()
        .setName("set-lastfm-username")
        .setDescription("Set your Last.fm username")
        .addStringOption((option) =>
            option
                .setName("username")
                .setDescription("Your Last.fm username")
                .setRequired(true),
        ),
    new SlashCommandBuilder()
        .setName("get-all-stats")
        .setDescription("Get all statistics for a given time period")
        .addStringOption((option) =>
            option
                .setName("timeframe")
                .setDescription("The timeframe to get statistics for")
                .setRequired(true)
                .addChoices(
                    timeframeOptions.map((tfoption) => [
                        tfoption.label,
                        tfoption.value,
                    ]),
                ),
        ),
    new SlashCommandBuilder()
        .setName("get-top-tracks")
        .setDescription("Get your top tracks for a given time period")
        .addStringOption((option) =>
            option
                .setName("timeframe")
                .setDescription("The timeframe to get statistics for")
                .setRequired(true)
                .addChoices(
                    timeframeOptions.map((tfoption) => [
                        tfoption.label,
                        tfoption.value,
                    ]),
                ),
        ),
    new SlashCommandBuilder()
        .setName("get-top-artists")
        .setDescription("Get your top artists for a given time period")
        .addStringOption((option) =>
            option
                .setName("timeframe")
                .setDescription("The timeframe to get statistics for")
                .setRequired(true)
                .addChoices(
                    timeframeOptions.map((tfoption) => [
                        tfoption.label,
                        tfoption.value,
                    ]),
                ),
        ),
    new SlashCommandBuilder()
        .setName("get-top-albums")
        .setDescription("Get your top albums for a given time period")
        .addStringOption((option) =>
            option
                .setName("timeframe")
                .setDescription("The timeframe to get statistics for")
                .setRequired(true)
                .addChoices(
                    timeframeOptions.map((tfoption) => [
                        tfoption.label,
                        tfoption.value,
                    ]),
                ),
        ),
    new SlashCommandBuilder()
        .setName("get-duration")
        .setDescription("Get your listening time for a given time period")
        .addStringOption((option) =>
            option
                .setName("timeframe")
                .setDescription("The timeframe to get statistics for")
                .setRequired(true)
                .addChoices(
                    timeframeOptions.map((tfoption) => [
                        tfoption.label,
                        tfoption.value,
                    ]),
                ),
        ),
    new SlashCommandBuilder()
        .setName("get-track-count")
        .setDescription(
            "Find out how many tracks you listened to in a given time period",
        )
        .addStringOption((option) =>
            option
                .setName("timeframe")
                .setDescription("The timeframe to get statistics for")
                .setRequired(true)
                .addChoices(
                    timeframeOptions.map((tfoption) => [
                        tfoption.label,
                        tfoption.value,
                    ]),
                ),
        ),
].map((command) => command.toJSON());

const rest = new REST({ version: "9" }).setToken(token);

// Uncomment the following to switch to deploying commands to only one server
// rest.put(Routes.applicationGuildCommands(clientId, guildId), { body: commands })
rest.put(Routes.applicationCommands(clientId), { body: commands })
    .then(() => console.log("Successfully registered application commands."))
    .catch(console.error);
