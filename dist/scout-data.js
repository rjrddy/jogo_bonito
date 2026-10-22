// Decoding for the packed scouting data files. Both files intern nationality
// codes and store counts positionally to keep the download small; everything
// downstream expects plain objects, so rehydration happens once here.
const POSITION_ORDER=['G','D','M','F'];

export function hydrateClubs(file){
 const byId=new Map(),byClub=new Map(),byYear=new Map();
 const list=file.clubs.map(row=>{
  const nations={};
  for(let i=0;i<row.nations.length;i+=2)nations[file.nation_codes[row.nations[i]]]=row.nations[i+1];
  const positions={};
  POSITION_ORDER.forEach((group,i)=>{positions[group]=row.positions[i]||0;});
  const {nations:_packed,positions:_counts,...rest}=row;
  return {...rest,nation_counts:nations,position_counts:positions};
 });
 for(const club of list){
  byId.set(club.id,club);
  if(!byClub.has(club.club))byClub.set(club.club,[]);
  byClub.get(club.club).push(club);
  if(!byYear.has(club.year))byYear.set(club.year,[]);
  byYear.get(club.year).push(club);
 }
 for(const editions of byClub.values())editions.sort((a,b)=>a.year-b.year);
 return {list,byId,byClub,byYear,nationCodes:file.nation_codes,as_of:file.as_of};
}

export function hydrateProspects(file,clubs){
 const index=Object.fromEntries(file.fields.map((name,i)=>[name,i]));
 return file.rows.map((row,position)=>({
  index:position,
  name:row[index.name],
  edition:file.editions[row[index.edition]],
  age:row[index.age],
  position:row[index.position],
  nationality:row[index.nationality]===null?null:file.nation_codes[row[index.nationality]],
  number:row[index.number],
  years_at_club:row[index.years_at_club],
  seasons_seen:row[index.seasons_seen],
  debut_age:row[index.debut_age],
  foreign:row[index.foreign],
  departed:row[index.departed],
  identity:row[index.identity],
  outcome:row[index.outcome],
  peak_edition:row[index.peak_edition]===null?null:file.editions[row[index.peak_edition]],
 }));
}

// The shape the feature builders expect, from either a pooled row or the form.
export function prospectRecord(prospect){
 return {name:prospect.name,age:prospect.age,position:prospect.position,nationality:prospect.nationality,
  number:prospect.number,years_at_club:prospect.years_at_club,seasons_seen:prospect.seasons_seen,
  debut_age:prospect.debut_age,foreign:prospect.foreign,status:prospect.departed?'departed':'listed'};
}
